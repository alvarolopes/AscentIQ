import { z } from 'zod';

export const sessionSchema = z.object({ username: z.string() });
export const snapshotSchema = z.looseObject({
  generated_at: z.string(),
  athlete: z.looseObject({ name: z.string() }),
  freshness: z.looseObject({ activities: z.string().nullable().optional() }),
  storage: z.looseObject({ backend: z.string().optional() }).optional(),
  sync_warnings: z.array(z.string()).optional(),
});
export type Snapshot = z.infer<typeof snapshotSchema>;

export const jobsSchema = z.object({
  jobs: z.array(
    z.looseObject({
      id: z.string(),
      status: z.string(),
      message: z.string().optional(),
    }),
  ),
});
export const loginSchema = z.object({
  username: z.string().trim().min(1, 'Informe o usuário.').max(80),
  password: z.string().min(1, 'Informe a senha.').max(256),
});

export type LoginValues = z.infer<typeof loginSchema>;
