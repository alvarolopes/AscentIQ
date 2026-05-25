from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "analysis" / "races"
DATA_DIR = ROOT / "data"
KEY_RACES_PATH = ANALYSIS_DIR / "key_races_fit_reanalysis.json"
MASTER_INDEX_PATH = DATA_DIR / "activity_master_index.json"

SLUGS = {
    "WTR Arraial do cabo": "2025-05-24_wtr_arraial_do_cabo_fit_first",
    "WTR Campos do Jordão - Ultramaratona 49km": "2025-10-04_wtr_campos_do_jordao_fit_first",
    "WTR Serra do mar - Ultra": "2025-11-15_wtr_serra_do_mar_fit_first",
    "WTR Floresta da Tijuca": "2026-03-14_wtr_rio_fit_first",
    "26° Meia Maratona Internacional do Rio de Janeiro": "2024-08-18_meia_rio_26_fit_first",
    "RJ Half Marathon": "2025-04-27_rj_half_marathon_fit_first",
    "Desafio da Ponte": "2025-08-03_desafio_da_ponte_fit_first",
    "27° Meia Maratona Internacional do Rio de Janeiro": "2025-08-17_meia_rio_27_fit_first",
    "Maratona de Niterói": "2024-09-01_maratona_de_niteroi_fit_first",
    "Maratona do Rio": "2025-06-22_maratona_do_rio_fit_first",
}

TRAIL_COMPARISONS = {
    "WTR Arraial do cabo": "Em relacao aos seus outros benchmarks de trilha, Arraial virou a referencia de custo compacto: mais cardiaco do que Campos e Serra, e com fechamento claramente pior do que Rio, Campos e Serra.",
    "WTR Campos do Jordão - Ultramaratona 49km": "Em relacao a Arraial, Campos mostra salto grande de economia para duracao longa. Em relacao a Serra, ele e menos brutal em D+ e por isso funciona melhor como benchmark de eficiencia do que de dureza absoluta.",
    "WTR Serra do mar - Ultra": "Em relacao a todo o seu historico, Serra do Mar e a prova mais proxima da logica de montanha longa: maior carga vertical real, maior duracao e capacidade de seguir funcional no final.",
    "WTR Floresta da Tijuca": "Em relacao a Arraial, o Rio mostra evolucao clara de reserva final. Em relacao a Campos e Serra, perde em duracao, mas ganha como retrato de agressividade vertical com energia ainda disponivel no fechamento.",
}

ROAD_COMPARISONS = {
    "26° Meia Maratona Internacional do Rio de Janeiro": "Hoje ela funciona como baseline historica. Quando comparada com a 27 Meia, mostra que houve evolucao real de performance e de capacidade de fechar bem a meia em 2025.",
    "RJ Half Marathon": "Comparada com as Meias do Rio e com a Ponte, esta foi uma meia mais controlada e menos representativa de teto competitivo. Ainda assim, ajuda a mostrar manutencao cardiovascular e bom fechamento.",
    "Desafio da Ponte": "Em relacao a 27 Meia, a Ponte foi um pouco mais lenta, mas continua muito util porque exige mais forca resistente e tolerancia a um percurso menos liso.",
    "27° Meia Maratona Internacional do Rio de Janeiro": "Entre as meias, essa segue como sua referencia principal. E a prova que melhor resume rendimento de meia em asfalto com execucao limpa e fechamento firme.",
    "Maratona de Niterói": "Entre as maratonas, Niteroi segue como a melhor expressao de maratona competitiva. A Maratona do Rio recente parece mais controlada e menos voltada a extrair teto de desempenho.",
    "Maratona do Rio": "Quando comparada a Niteroi, a Maratona do Rio mostra um custo cardiovascular menor e uma execucao mais conservadora. Ela vale mais como referencia de endurance sustentado do que de performance maxima.",
}

AREQUIPA_TRANSFER = {
    "WTR Arraial do cabo": "Transferencia moderada: muito util para custo mecanico de trilha, mas abaixo do que Arequipa pede em duracao longa e continuidade vertical.",
    "WTR Campos do Jordão - Ultramaratona 49km": "Transferencia alta: excelente referencia de economia em trilha longa e de tolerancia a horas continuas de esforco.",
    "WTR Serra do mar - Ultra": "Transferencia muito alta: melhor espelho local de montanha longa antes da altitude real.",
    "WTR Floresta da Tijuca": "Transferencia alta: mostra que voce consegue chegar ao final de uma trilha vertical ainda com energia funcional.",
    "26° Meia Maratona Internacional do Rio de Janeiro": "Transferencia indireta: ajuda mais a contar a historia do seu motor aerobico do que a simular montanha.",
    "RJ Half Marathon": "Transferencia indireta: serve como manutencao competitiva e leitura cardiovascular, nao como simulador de montanha.",
    "Desafio da Ponte": "Transferencia indireta a moderada: e mais util para forca resistente do que uma meia totalmente plana.",
    "27° Meia Maratona Internacional do Rio de Janeiro": "Transferencia indireta: excelente como prova de motor e limiar sustentado, mas nao substitui vertical e hike tecnico.",
    "Maratona de Niterói": "Transferencia moderada: boa para comprovar fundo e resistencia longa, mas sem especificidade de montanha.",
    "Maratona do Rio": "Transferencia moderada: sustenta o fundo geral, mas o principal valor para Arequipa continua sendo chegar inteiro, nao correr maratona por desempenho.",
}

PRACTICAL_RECOMMENDATIONS = {
    "WTR Arraial do cabo": "Usar Arraial como referencia de quanto o terreno compacto pode cobrar de voce e buscar, nos treinos, terminar melhor do que terminou aqui.",
    "WTR Campos do Jordão - Ultramaratona 49km": "Usar Campos como benchmark de economia em ultra trail e perseguir nos treinos a mesma combinacao de baixa parada, FC controlada e fechamento vivo.",
    "WTR Serra do mar - Ultra": "Usar Serra do Mar como benchmark principal para qualquer comparacao de montanha longa e trabalhar continuidade de vertical para aproximar mais essa qualidade de Arequipa.",
    "WTR Floresta da Tijuca": "Transformar a qualidade central do Rio em treino: subir controlado e ainda ter perna para correr no final.",
    "26° Meia Maratona Internacional do Rio de Janeiro": "Manter esta prova como baseline historica e usar as meias mais recentes como referencia principal de estado atual.",
    "RJ Half Marathon": "Usar esta meia mais como referencia de manutencao controlada do que como prova de teto de performance.",
    "Desafio da Ponte": "Tratar a Ponte como referencia de forca resistente e encaixar treinos ondulados quando quiser estimular isso sem depender de trilha.",
    "27° Meia Maratona Internacional do Rio de Janeiro": "Usar a 27 Meia como benchmark principal de meia e como referencia de que seu motor de asfalto esta bem sustentado.",
    "Maratona de Niterói": "Manter Niteroi como referencia de maratona competitiva e usar esse padrao quando quiser avaliar quanto do seu fundo e realmente competitivo.",
    "Maratona do Rio": "Ler a Maratona do Rio como prova de endurance controlado e nao cobrar dela o mesmo papel competitivo de Niteroi.",
}

WHAT_FIT_CHANGED = {
    "WTR Arraial do cabo": "O FIT mudou bastante a leitura porque derrubou o mito do tempo parado alto e, ao mesmo tempo, confirmou que o fechamento foi realmente pior.",
    "WTR Campos do Jordão - Ultramaratona 49km": "O FIT confirmou que Campos foi limpo, economico e quase sem interrupcao, fortalecendo muito o valor dela como benchmark de eficiencia.",
    "WTR Serra do mar - Ultra": "O FIT mostrou uma prova mais continua do que o resumo antigo sugeria, o que reforca ainda mais a qualidade da sua resistencia nessa ultra.",
    "WTR Floresta da Tijuca": "O FIT foi decisivo aqui porque provou, por trecho, que houve aceleracao real no fim da prova.",
    "26° Meia Maratona Internacional do Rio de Janeiro": "O FIT confirmou que a prova foi limpa e praticamente sem interrupcoes, consolidando bem a baseline de 2024.",
    "RJ Half Marathon": "O FIT melhorou a leitura de fechamento, mas tambem reforcou que a altimetria dessa prova nao e boa referencia.",
    "Desafio da Ponte": "O FIT confirmou a consistencia da prova e um fechamento firme sem precisar exagerar a altimetria.",
    "27° Meia Maratona Internacional do Rio de Janeiro": "O FIT consolidou a 27 Meia como sua meia mais limpa e mais forte dentro do historico recente.",
    "Maratona de Niterói": "O FIT mostrou uma maratona muito limpa e praticamente sem paradas, melhorando a confianca nela como benchmark.",
    "Maratona do Rio": "O FIT deixou mais claro que esta maratona foi controlada e organizada, e nao uma tentativa de extrair seu teto competitivo.",
}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower().replace(" ", "_")


def fmt_num(value: float | int | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def seconds_to_hms(seconds: float | int | None) -> str:
    if seconds is None:
        return "n/a"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def pct_stopped(stopped_s: float | None, elapsed: str | None) -> float | None:
    if stopped_s is None or not elapsed:
        return None
    h, m, s = [int(x) for x in elapsed.split(":")]
    total = h * 3600 + m * 60 + s
    if total <= 0:
        return None
    return round(100 * stopped_s / total, 1)


def build_summary_line(item: dict[str, Any], activity_lookup: dict[str, dict[str, Any]]) -> list[str]:
    fit = item["fit_primary"]
    finish = item["finish_signature"]
    course = item["course_profile"]
    activity = activity_lookup[item["name"]]
    lines = [
        f"- Data: {item['date']}",
        f"- Distancia FIT: {fmt_num(fit['distance_km'], 3)} km",
        f"- Tempo total FIT: {fit['elapsed_time']}",
        f"- Tempo em movimento FIT: {fit['moving_time']}",
        f"- Tempo parado FIT: {fit['stopped_time']} ({fmt_num(pct_stopped(fit['stopped_time_seconds'], fit['elapsed_time']), 1)}%)",
        f"- FC media/max FIT: {fit['avg_hr']} / {fit['max_hr']} bpm",
        f"- Relative Effort: {activity.get('relative_effort')}",
        f"- Training Load: {activity.get('training_load')}",
        f"- Assinatura final FIT: {finish['signature']}",
    ]
    if item["category"] == "trail":
        if course.get("official_gain_m") is not None:
            lines.append(f"- D+ oficial do percurso: {fmt_num(course['official_gain_m'], 1)} m")
        lines.append(f"- D+ FIT do relogio: {fmt_num(fit['ascent_m'], 1)} m")
    else:
        lines.append(f"- D+ FIT do relogio: {fmt_num(fit['ascent_m'], 1)} m")
    return lines


def build_physiology(item: dict[str, Any], activity_lookup: dict[str, dict[str, Any]]) -> list[str]:
    fit = item["fit_primary"]
    activity = activity_lookup[item["name"]]
    lines: list[str] = []
    effort = activity.get("relative_effort")
    load = activity.get("training_load")
    if item["category"] == "trail":
        lines.append("- O esforco foi tipicamente de montanha: mais importante pela sustentabilidade do desgaste do que por velocidade pura.")
    else:
        lines.append("- O esforco foi lido pelo FIT como prova limpa e continua, sem depender de tempo parado para explicar o resultado.")
    lines.append(f"- A combinacao de FC media {fit['avg_hr']}, Relative Effort {effort} e Training Load {load} define bem o custo interno dessa prova.")
    lines.append(f"- A eficiencia cardiaca FIT ficou em {fmt_num(fit['heart_rate_efficiency'], 3)}, valor que entra agora na sua base real de comparacao.")
    lines.append(f"- O que o FIT mudou aqui: {WHAT_FIT_CHANGED[item['name']]}")
    return lines


def build_terrain(item: dict[str, Any]) -> list[str]:
    fit = item["fit_primary"]
    course = item["course_profile"]
    lines: list[str] = []
    if item["category"] == "trail":
        if course.get("official_gain_m") is not None:
            lines.append(f"- Para essa prova, o D+ oficial do percurso deve prevalecer: {fmt_num(course['official_gain_m'], 1)} m, contra {fmt_num(fit['ascent_m'], 1)} m no FIT.")
            lines.append(f"- A diferenca oficial - FIT foi de {fmt_num(course['official_minus_fit_gain_m'], 1)} m, entao o relogio sozinho distorceria a leitura do terreno.")
        lines.append(f"- A densidade vertical pelo FIT ficou em {fmt_num(fit['vertical_per_km'], 2)} m/km, mas a interpretacao final do terreno deve continuar ancorada no percurso oficial.")
    else:
        lines.append("- Em prova de rua, a altimetria do relogio entra apenas como contexto secundario.")
        lines.append(f"- O FIT marcou {fmt_num(fit['ascent_m'], 1)} m de subida, mas esse numero nao deve ser usado como benchmark forte de D+ em asfalto.")
    return lines


def build_comparison(item: dict[str, Any]) -> list[str]:
    finish = item["finish_signature"]
    lines = [
        f"- Fechamento FIT: ultimos 5 km em {finish['last_5k_pace']} contra {finish['previous_5k_pace']} no bloco anterior, variacao de {fmt_num(finish['last_5k_gain_s_per_km'], 1)} s/km.",
        f"- Ultimos 2 km em {finish['last_2k_pace']} contra {finish['previous_2k_pace']}, variacao de {fmt_num(finish['last_2k_gain_s_per_km'], 1)} s/km.",
    ]
    if item["category"] == "trail":
        lines.append(f"- {TRAIL_COMPARISONS[item['name']]}")
    else:
        lines.append(f"- {ROAD_COMPARISONS[item['name']]}")
    return lines


def build_impact(item: dict[str, Any]) -> list[str]:
    return [
        f"- {AREQUIPA_TRANSFER[item['name']]}",
        "- No seu modelo atual, a pergunta principal nao e se a prova foi rapida, e sim o que ela prova sobre sua capacidade de completar bem e seguir funcional sob fadiga.",
    ]


def build_recommendation(item: dict[str, Any]) -> list[str]:
    return [
        f"- {PRACTICAL_RECOMMENDATIONS[item['name']]}",
        "- Esta prova deve permanecer na memoria do agente como benchmark fixo e ser usada nas proximas comparacoes relevantes.",
    ]


def build_payload(item: dict[str, Any], activity_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "date": item["date"],
        "name": item["name"],
        "category": item["category"],
        "role": item["role"],
        "fit_primary": item["fit_primary"],
        "course_profile": item["course_profile"],
        "finish_signature": item["finish_signature"],
        "sections": {
            "summary": build_summary_line(item, activity_lookup),
            "physiology": build_physiology(item, activity_lookup),
            "terrain": build_terrain(item),
            "comparison": build_comparison(item),
            "impact": build_impact(item),
            "recommendation": build_recommendation(item),
        },
    }


def payload_to_markdown(payload: dict[str, Any]) -> str:
    sections = payload["sections"]
    title = payload["name"]
    lines = [f"# {title} - FIT First", "", f"Gerado em: {datetime.now().astimezone().isoformat(timespec='seconds')}", ""]
    lines.append("## 1. Resumo da atividade")
    lines.extend(sections["summary"])
    lines.append("")
    lines.append("## 2. Leitura fisiologica")
    lines.extend(sections["physiology"])
    lines.append("")
    lines.append("## 3. Leitura do terreno")
    lines.extend(sections["terrain"])
    lines.append("")
    lines.append("## 4. Comparacao com historico")
    lines.extend(sections["comparison"])
    lines.append("")
    lines.append("## 5. Impacto no objetivo do ano")
    lines.extend(sections["impact"])
    lines.append("")
    lines.append("## 6. Recomendacao pratica")
    lines.extend(sections["recommendation"])
    lines.append("")
    lines.append("## 7. Fonte principal")
    lines.append("- FIT como fonte principal de tempos, FC, tempo parado e dinamica de fechamento.")
    if payload["category"] == "trail":
        lines.append("- GPX oficial ou dado manual oficial como fonte principal de D+ quando disponivel.")
    else:
        lines.append("- D+ de rua mantido apenas como contexto secundario, nao como benchmark forte.")
    return "\n".join(lines) + "\n"


def build_index(dossiers: list[dict[str, str]]) -> str:
    lines = [
        "# Key Race FIT Dossiers",
        "",
        f"Gerado em: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## Trilhas",
    ]
    for item in dossiers:
        if item["category"] == "trail":
            lines.append(f"- {item['date']} | {item['name']} | {item['role']} | {item['md_name']}")
    lines.append("")
    lines.append("## Rua")
    for item in dossiers:
        if item["category"] == "road":
            lines.append(f"- {item['date']} | {item['name']} | {item['role']} | {item['md_name']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    key_races = load_json(KEY_RACES_PATH)
    master = load_json(MASTER_INDEX_PATH)
    activity_lookup = {item["name"]: item for item in master}

    dossiers: list[dict[str, str]] = []
    all_items = key_races["trail_races"] + key_races["road_races"]
    for item in all_items:
        payload = build_payload(item, activity_lookup)
        stem = SLUGS[item["name"]]
        json_path = ANALYSIS_DIR / f"{stem}.json"
        md_path = ANALYSIS_DIR / f"{stem}.md"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(payload_to_markdown(payload), encoding="utf-8")
        dossiers.append({
            "date": item["date"],
            "name": item["name"],
            "category": item["category"],
            "role": item["role"],
            "md_name": md_path.name,
        })

    index_path = ANALYSIS_DIR / "key_race_fit_dossiers_index.md"
    index_path.write_text(build_index(dossiers), encoding="utf-8")
    print(f"Wrote {len(dossiers)} dossiers and {index_path}")


if __name__ == "__main__":
    main()
