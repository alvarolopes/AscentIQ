"""Private, idempotent activity/file imports with reversible source reconciliation.

Client filenames are metadata only. All original paths are generated from digests;
no importer accepts a local path. Operational state is transactionally versioned.
"""
from __future__ import annotations

import base64
import binascii
import copy
import csv
import hashlib
import io
import json
import math
import re
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from dashboard.repository import operational_db, read_dataset

MAX_BYTES = 12 * 1024 * 1024
MAX_ROWS = 10000
MAX_POINTS = 100000
FIELDS = ("date", "date_time", "type", "name", "duration_seconds", "distance_km",
          "elevation_gain_m", "avg_hr", "max_hr", "calories", "moving_time_seconds",
          "hevy_workout_id", "garmin_activity_id")
NAMESPACE = uuid.UUID("94232e91-10f7-4b2b-97b6-d6f01146c4a3")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def _uid(value):
    return str(uuid.uuid5(NAMESPACE, value))


def _known(value):
    return value is not None and value != ""


def _number(value, field, *, required=False, positive=False):
    if value is None or str(value).strip().lower() in {"", "null", "none"}:
        if required:
            raise ValueError(f"Campo obrigatório: {field}.")
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Valor inválido em {field}.") from exc
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f"Valor inválido em {field}.")
    return result


def _event_time(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("Data obrigatória.")
    try:
        if len(text) == 10:
            return date.fromisoformat(text).isoformat(), None
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return stamp.date().isoformat(), stamp.isoformat()
    except ValueError as exc:
        raise ValueError("Data deve ser ISO 8601; inclua o fuso quando conhecido.") from exc


def _kind(value):
    token = str(value or "").lower().replace("_", " ")
    if any(x in token for x in ("run", "corrida", "trail")):
        return "running"
    if any(x in token for x in ("weight", "strength", "força", "forca", "muscul")):
        return "strength"
    if any(x in token for x in ("bike", "cycl", "cicl")):
        return "cycling"
    if any(x in token for x in ("walk", "hike", "hiking", "caminh", "mountain")):
        return "hiking"
    if any(x in token for x in ("swim", "nat")):
        return "swimming"
    return "other"


def _duration(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _number(value, "duration_seconds")
    try:
        total = 0.0
        for part in str(value).split(":"):
            total = total * 60 + float(part)
        return total if math.isfinite(total) and total >= 0 else None
    except ValueError:
        return None


def _csv_records(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    required = {"id", "date", "type", "duration_seconds"}
    fields = reader.fieldnames or []
    if len(fields) != len(set(fields)) or not required.issubset(fields):
        raise ValueError("CSV requer cabeçalho id,date,type,duration_seconds; use o modelo documentado.")
    records, seen = [], set()
    for ordinal, row in enumerate(reader, 2):
        if ordinal > MAX_ROWS + 1:
            raise ValueError("CSV excede o limite de registros.")
        if None in row:
            raise ValueError(f"Linha CSV {ordinal} tem colunas extras.")
        external_id = str(row.get("id") or "").strip()
        if not external_id or len(external_id) > 200 or external_id in seen:
            raise ValueError(f"Identificador ausente/repetido na linha {ordinal}.")
        seen.add(external_id)
        day, stamp = _event_time(row.get("date"))
        if row.get("date_time"):
            timed_day, timed_stamp = _event_time(row["date_time"])
            if timed_stamp is None or timed_day != day:
                raise ValueError(f"date_time deve conter horário e concordar com date na linha {ordinal}.")
            stamp = timed_stamp
        modality = str(row.get("type") or "").strip()
        if not modality or len(modality) > 80:
            raise ValueError(f"Modalidade inválida na linha {ordinal}.")
        record = {"id": _uid("csv:" + external_id), "external_id": external_id,
                  "format": "csv", "date": day, "date_time": stamp, "type": modality,
                  "name": str(row.get("name")).strip()[:300] if row.get("name") else None,
                  "duration_seconds": _number(row.get("duration_seconds"), "duration_seconds", required=True)}
        for field in ("distance_km", "elevation_gain_m", "avg_hr", "max_hr", "calories"):
            record[field] = _number(row.get(field), field)
        records.append(record)
    if not records:
        raise ValueError("CSV não contém atividades.")
    return records, []


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _distance(a, b):
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    delta_lat, delta_lon = lat2 - lat1, math.radians(b["lon"] - a["lon"])
    h = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def _gpx_routes(raw):
    if re.search(br"<!\s*(DOCTYPE|ENTITY)", raw, re.I):
        raise ValueError("GPX não aceita DTD nem entidades externas.")
    try:
        document = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("XML GPX inválido.") from exc
    if _local(document.tag) != "gpx":
        raise ValueError("O documento precisa ter raiz GPX.")
    segments = [element for element in document.iter() if _local(element.tag) in {"trkseg", "rte"}]
    points, distance, ascent, has_elevation = [], 0.0, 0.0, False
    for segment_index, segment in enumerate(segments):
        previous = None
        for element in segment:
            if _local(element.tag) not in {"trkpt", "rtept"}:
                continue
            try:
                lat, lon = float(element.attrib["lat"]), float(element.attrib["lon"])
            except (KeyError, ValueError) as exc:
                raise ValueError("Coordenada GPX inválida.") from exc
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Coordenada GPX fora do intervalo válido.")
            point = {"lat": lat, "lon": lon, "segment": segment_index}
            for child in element:
                if _local(child.tag) == "ele" and child.text:
                    try:
                        elevation = float(child.text)
                    except ValueError as exc:
                        raise ValueError("Elevação GPX inválida.") from exc
                    if not math.isfinite(elevation):
                        raise ValueError("Elevação GPX inválida.")
                    point["elevation_m"] = elevation
                    has_elevation = True
                if _local(child.tag) == "time" and child.text:
                    _, point["time"] = _event_time(child.text)
            if previous:
                distance += _distance(previous, point)
                if "elevation_m" in previous and "elevation_m" in point:
                    ascent += max(0, point["elevation_m"] - previous["elevation_m"])
            points.append(point)
            previous = point
            if len(points) > MAX_POINTS:
                raise ValueError("GPX excede o limite de pontos.")
    if len(points) < 2:
        raise ValueError("GPX requer ao menos dois pontos de percurso.")
    name = next((element.text for element in document.iter() if _local(element.tag) == "name" and element.text), "Percurso importado")
    digest = hashlib.sha256(raw).hexdigest()
    return [], [{"id": _uid("gpx:" + digest), "name": name[:300], "format": "gpx", "kind": "route",
                 "execution_evidence": False, "distance_km": round(distance / 1000, 4),
                 "elevation_gain_m": round(ascent, 1) if has_elevation else None,
                 "elevation_method": "sum_positive_deltas_no_smoothing", "point_count": len(points), "points": points}]


def _fit_records(raw):
    if len(raw) < 14 or raw[8:12] != b".FIT":
        raise ValueError("Cabeçalho FIT inválido.")
    try:
        import fitdecode
    except ImportError as exc:
        raise ValueError("Leitura FIT indisponível; instale as dependências publicadas do projeto.") from exc
    sessions, identity = [], {}
    try:
        with fitdecode.FitReader(io.BytesIO(raw), check_crc=fitdecode.CrcCheck.RAISE,
                                 error_handling=fitdecode.ErrorHandling.RAISE) as reader:
            for frame in reader:
                if isinstance(frame, fitdecode.FitDataMessage):
                    values = {field.name: field.value for field in frame.fields}
                    if frame.name == "file_id":
                        identity = values
                    elif frame.name == "session":
                        sessions.append(values)
                        if len(sessions) > MAX_ROWS:
                            raise ValueError("FIT excede o limite de sessões.")
    except Exception as exc:
        raise ValueError("Arquivo FIT inválido ou incompleto.") from exc
    records = []
    for index, session in enumerate(sessions):
        start = session.get("start_time")
        if not start:
            raise ValueError("Resumo FIT sem horário de início.")
        day, stamp = _event_time(start.isoformat() if isinstance(start, datetime) else start)
        modality = str(session.get("sport") or "Activity")
        external = _canonical([identity.get("serial_number"), stamp, modality, index])
        duration = session.get("total_elapsed_time")
        if duration is None:
            duration = session.get("total_timer_time")
        record = {"id": _uid("fit:" + external), "external_id": external, "format": "fit",
                  "date": day, "date_time": stamp, "type": modality, "name": modality,
                  "duration_seconds": _number(duration, "duration_seconds", required=True),
                  "moving_time_seconds": _number(session.get("total_timer_time"), "moving_time_seconds")}
        for field, original in (("elevation_gain_m", "total_ascent"), ("avg_hr", "avg_heart_rate"),
                                ("max_hr", "max_heart_rate"), ("calories", "total_calories")):
            record[field] = _number(session.get(original), field)
        distance = _number(session.get("total_distance"), "total_distance")
        record["distance_km"] = distance / 1000 if distance is not None else None
        records.append(record)
    if not records:
        raise ValueError("FIT precisa conter ao menos um resumo de sessão executada.")
    return records, []


class ImportService:
    def __init__(self, runtime, root):
        self.runtime, self.root = Path(runtime), Path(root)
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.originals = self.runtime / "personal-imports"
        if self.originals.is_symlink():
            raise ValueError("Diretório de originais não pode ser um vínculo externo.")
        self.originals.mkdir(parents=True, exist_ok=True)
        if not self.originals.resolve().is_relative_to(self.runtime.resolve()):
            raise ValueError("Diretório de originais fora do ambiente privado.")
        with operational_db(self.runtime, "imports", self.root) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS personal_imports_state (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    @staticmethod
    def _empty():
        return {"schema_version": 1, "revision": 0, "imports": [], "records": {}, "routes": {}, "links": [], "distinct_pairs": []}

    def _load(self, conn):
        row = conn.execute("SELECT payload FROM personal_imports_state WHERE id=?", ("state",)).fetchone()
        return json.loads(row[0]) if row else self._empty()

    def _save(self, conn, state, event):
        state["revision"] += 1
        event = {**event, "revision": state["revision"], "recorded_at": _now()}
        conn.execute("INSERT INTO personal_imports_state(id,payload) VALUES(?,?)",
                     (f"revision:{state['revision']:010d}", _canonical(event)))
        conn.execute("INSERT INTO personal_imports_state(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                     ("state", _canonical(state)))

    def _legacy(self):
        result = {}
        for index, row in enumerate(read_dataset(self.root, "data/training_history.json", []) or []):
            legacy_id = str(row.get("garmin_activity_id") or row.get("activity_key") or f"local-{index}")
            rid = "legacy:" + legacy_id
            record = {**row, "id": rid, "legacy_id": legacy_id, "format": "legacy",
                      "duration_seconds": _duration(row.get("duration_seconds") if row.get("duration_seconds") is not None else row.get("elapsed_time")),
                      "elevation_gain_m": row.get("official_elevation_gain_m") if row.get("official_elevation_gain_m") is not None else row.get("watch_elevation_gain_m"),
                      "sources": [{"format": "legacy", "external_id": legacy_id, "source": row.get("source"), "record_id": rid}]}
            result[rid] = record
        return result

    def import_file(self, format, filename, content):
        format = str(format or "").lower().strip()
        if format not in {"csv", "gpx", "fit"}:
            raise ValueError("Formato aceito: csv, gpx ou fit.")
        filename = str(filename or "")
        if not filename or len(filename) > 200 or any(x in filename for x in ("/", "\\", ":", "\x00")) or filename in {".", ".."}:
            raise ValueError("Nome de arquivo inválido; não forneça caminhos.")
        if not filename.lower().endswith("." + format):
            raise ValueError("Extensão deve corresponder ao formato informado.")
        if not isinstance(content, str):
            raise ValueError("Conteúdo deve ser texto; FIT requer base64.")
        if len(content) > MAX_BYTES * 2:
            raise ValueError("Arquivo excede o limite de tamanho.")
        if format == "fit":
            try:
                raw = base64.b64decode(content, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("FIT deve usar base64 válido, sem prefixo data:.") from exc
        else:
            raw = content.encode("utf-8")
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError("Arquivo vazio ou acima do limite de tamanho.")
        digest = hashlib.sha256(raw).hexdigest()
        import_id = _uid(format + ":" + digest)
        with operational_db(self.runtime, "imports", self.root) as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = self._load(conn)
            prior = next((item for item in state["imports"] if item["id"] == import_id), None)
            if prior:
                view = self._view(state)
                return {**view, "import": prior, "repeated": True}
            records, routes = {"csv": _csv_records, "gpx": _gpx_routes, "fit": _fit_records}[format](raw)
            for record in records:
                previous = state["records"].get(record["id"], {})
                if previous.get("date_time") and previous.get("date") != record["date"] and not record.get("date_time"):
                    raise ValueError("Ao corrigir a data de uma atividade com horário conhecido, informe também o novo horário.")
            original = self.originals / (digest + "." + format)
            if original.exists():
                if original.is_symlink() or hashlib.sha256(original.read_bytes()).hexdigest() != digest:
                    raise ValueError("Original armazenado falhou na verificação de integridade.")
            else:
                with original.open("xb") as stream:
                    stream.write(raw)
            observed_at, changed = _now(), []
            for record in records:
                rid = record["id"]
                previous = state["records"].get(rid, {})
                source = {"import_id": import_id, "record_id": rid, "format": format, "external_id": record["external_id"],
                          "sha256": digest, "filename": filename, "received_at": observed_at,
                          "values": {k: record.get(k) for k in FIELDS if _known(record.get(k))}}
                merged = {**previous, **{k: v for k, v in record.items() if _known(v)}}
                merged["sources"] = list(previous.get("sources", [])) + [source]
                merged["field_sources"] = {**previous.get("field_sources", {}), **{k: import_id for k in FIELDS if _known(record.get(k))}}
                state["records"][rid] = merged
                changed.append(copy.deepcopy(merged))
            for route in routes:
                route["sources"] = [{"import_id": import_id, "sha256": digest, "filename": filename, "format": format}]
                state["routes"][route["id"]] = route
            receipt = {"id": import_id, "format": format, "filename": filename, "sha256": digest, "bytes": len(raw),
                       "status": "complete", "imported_at": observed_at, "record_ids": [r["id"] for r in records],
                       "route_ids": [r["id"] for r in routes], "activity_count": len(records), "route_count": len(routes)}
            state["imports"].append(receipt)
            self._save(conn, state, {"operation": "import", "receipt": receipt, "records": changed, "routes": routes})
            return {**self._view(state), "import": receipt, "repeated": False}

    def _view(self, state):
        legacy = self._legacy()
        all_records = {**legacy, **state["records"]}
        parent = {rid: rid for rid in all_records}

        def find(rid):
            while parent[rid] != rid:
                rid = parent[rid]
            return rid

        for link in state["links"]:
            a, b = link["record_id"], link["other_id"]
            if a in parent and b in parent:
                primary, secondary = find(a), find(b)
                if primary != secondary:
                    parent[secondary] = primary
        groups: dict = {}
        for rid in all_records:
            groups.setdefault(find(rid), []).append(rid)
        records, suppressed = [], []
        for primary, members in groups.items():
            if not any(rid in state["records"] for rid in members):
                continue
            order = [primary] + sorted(rid for rid in members if rid != primary)
            result = copy.deepcopy(all_records[primary])
            field_sources, observation_sources, conflicts, sources = {}, {}, {}, []
            for field in FIELDS:
                options = [(rid, all_records[rid][field]) for rid in order if _known(all_records[rid].get(field))]
                if options:
                    result[field], field_sources[field] = options[0][1], options[0][0]
                    origin_id = options[0][0]
                    observation_sources[field] = {"record_id": origin_id,
                                                  "import_id": all_records[origin_id].get("field_sources", {}).get(field)}
                    if len({_canonical(value) for _, value in options}) > 1:
                        conflicts[field] = [{"record_id": rid, "value": value} for rid, value in options]
            for rid in order:
                sources.extend(copy.deepcopy(all_records[rid].get("sources", [])))
            result.update(id=primary, kind=_kind(result.get("type")), linked_record_ids=order, sources=sources,
                          field_sources=field_sources, conflicts=conflicts,
                          field_observation_sources=observation_sources,
                          legacy_refs=[legacy[rid]["legacy_id"] for rid in members if rid in legacy])
            result["name"] = result.get("name") or result.get("type") or "Atividade importada"
            result["watch_elevation_gain_m"] = result.get("elevation_gain_m")
            seconds = result.get("duration_seconds")
            if seconds is not None:
                h, remainder = divmod(int(seconds), 3600)
                m, s = divmod(remainder, 60)
                result["elapsed_time"] = f"{h:02}:{m:02}:{s:02}"
            result["source"] = "+".join(sorted({str(x.get("source") or x.get("format")) for x in sources}))
            records.append(result)
            suppressed.extend(result["legacy_refs"])
        candidates: list = []
        visible = [*records, *[row for rid, row in legacy.items() if legacy[rid]["legacy_id"] not in suppressed]]
        buckets: dict = {}
        for row in visible:
            buckets.setdefault((row.get("date"), _kind(row.get("type"))), []).append(row)
        truncated = False
        distinct_pairs = {tuple(pair) for pair in state.get("distinct_pairs", [])}
        for bucket in buckets.values():
            for index, left in enumerate(bucket):
                if left["id"].startswith("legacy:"):
                    continue
                for right in bucket[index + 1:]:
                    if tuple(sorted((left["id"], right["id"]))) in distinct_pairs:
                        continue
                    a, b = left.get("duration_seconds"), right.get("duration_seconds")
                    if a is not None and b is not None and abs(a - b) > max(300, max(a, b) * .15):
                        continue
                    if len(candidates) >= 2000:
                        truncated = True
                        break
                    candidates.append({"record_id": left["id"], "other_id": right["id"], "status": "ambiguous",
                                       "reason": "Mesmo dia e modalidade; conferir horário, duração e origem antes de unir."})
                if truncated:
                    break
            if truncated:
                break
        return {"schema_version": 1, "revision": state["revision"], "imports": copy.deepcopy(state["imports"]),
                "records": sorted(records, key=lambda x: (x.get("date") or "", x.get("date_time") or ""), reverse=True),
                "routes": list(copy.deepcopy(state["routes"]).values()), "links": copy.deepcopy(state["links"]),
                "distinct_pairs": copy.deepcopy(state.get("distinct_pairs", [])),
                "source_records": list(copy.deepcopy(state["records"]).values()),
                "legacy_candidates": [{k: row.get(k) for k in ("id", "legacy_id", "date", "date_time", "type", "name", "duration_seconds")} for row in legacy.values()],
                "reconciliation": candidates, "reconciliation_truncated": truncated, "suppressed_legacy_ids": sorted(set(suppressed))}

    def read(self):
        with operational_db(self.runtime, "imports", self.root) as conn:
            state = self._load(conn)
        return self._view(state)

    def reconcile(self, record_id, action, other_id=None):
        action = {"link": "merge", "unmerge": "unlink"}.get(action, action)
        if action not in {"merge", "unlink", "keep"}:
            raise ValueError("Ação deve ser merge, unlink ou keep.")
        with operational_db(self.runtime, "imports", self.root) as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = self._load(conn)
            ids = set(state["records"]) | set(self._legacy())
            if record_id not in ids or (other_id is not None and other_id not in ids):
                raise ValueError("Atividade não encontrada.")
            if action in {"merge", "keep"}:
                if not other_id or record_id == other_id:
                    raise ValueError("Escolha duas atividades diferentes.")
                if record_id not in state["records"] and other_id not in state["records"]:
                    raise ValueError("Este fluxo vincula importações; não altera a consolidação legada.")
                view = self._view(state)
                already_linked = any(record_id in row["linked_record_ids"] and other_id in row["linked_record_ids"] for row in view["records"])
                pair = sorted((record_id, other_id))
                distinct = state.setdefault("distinct_pairs", [])
                if action == "keep":
                    if already_linked:
                        raise ValueError("Desfaça o vínculo antes de manter as atividades separadas.")
                    if pair in distinct:
                        return view
                    distinct.append(pair)
                else:
                    if already_linked:
                        return view
                    state["distinct_pairs"] = [existing for existing in distinct if existing != pair]
                    state["links"].append({"record_id": record_id, "other_id": other_id, "linked_at": _now()})
            else:
                previous = state["links"]
                if other_id:
                    state["links"] = [edge for edge in previous if {edge["record_id"], edge["other_id"]} != {record_id, other_id}]
                else:
                    state["links"] = [edge for edge in previous if record_id not in (edge["record_id"], edge["other_id"])]
                if state["links"] == previous:
                    return self._view(state)
            self._save(conn, state, {"operation": "reconcile", "action": action, "record_id": record_id,
                                     "other_id": other_id, "links": copy.deepcopy(state["links"]),
                                     "distinct_pairs": copy.deepcopy(state.get("distinct_pairs", []))})
            return self._view(state)

    def overlay(self, snapshot):
        result = copy.deepcopy(snapshot)
        view = self.read()
        suppressed = set(view["suppressed_legacy_ids"])
        originals = {str(row.get("id")): row for row in result.get("activities", [])}
        activities = [row for row in result.get("activities", []) if str(row.get("id")) not in suppressed]
        for record in view["records"]:
            baseline: dict = next((originals[ref] for ref in record["legacy_refs"] if ref in originals), {})
            activities.append({**baseline, **record})
        activities.sort(key=lambda x: (x.get("date") or "", x.get("date_time") or ""), reverse=True)
        result["activities"], result["routes"], result["imports"] = activities, view["routes"], view
        week = result.get("week", {})
        start, end = week.get("start"), week.get("end") or result.get("as_of")
        if start and end:
            recent = [row for row in activities if start <= (row.get("date") or "") <= end]
            week.update(activity_count=len(recent), minutes=round(sum(row.get("duration_seconds") or 0 for row in recent) / 60),
                        running_km=round(sum(row.get("distance_km") or 0 for row in recent if row.get("kind") == "running"), 2),
                        running_elevation_m=round(sum(row.get("elevation_gain_m") or 0 for row in recent if row.get("kind") == "running")),
                        by_kind=dict(Counter(row.get("kind") or _kind(row.get("type")) for row in recent)))
        if view["records"]:
            result.setdefault("freshness", {})["activities"] = max((row.get("date") or "" for row in activities), default=None)
            result["source_digest"] = hashlib.sha256((str(result.get("source_digest") or "") + _canonical({"records": view["records"], "revision": view["revision"]})).encode()).hexdigest()
            result.setdefault("performance", {}).setdefault("notes", []).append("Importações pessoais entram no diário; o modelo legado de carga permanece identificado pela versão original até reprocessamento específico.")
        return result
