import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';
// The 2020-12 build, not the default draft-07 one — entry.schema.json declares
// $schema as 2020-12 and plain `ajv` rejects that dialect.
import Ajv from 'ajv/dist/2020.js';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// The frontmatter rules live in exactly one place. This build validates against
// the same file the generator validates against before it opens a PR, so the
// `kind` enum cannot drift between Python and TypeScript.
const schemaPath = fileURLToPath(
  new URL('../../../content/schema/entry.schema.json', import.meta.url),
);
const entrySchema = JSON.parse(readFileSync(schemaPath, 'utf8'));

const ajv = new Ajv({ allErrors: true, strict: false });
const validateEntry = ajv.compile(entrySchema);

export type EntryKind =
  | 'travel'
  | 'new_job'
  | 'continuation'
  | 'resolution'
  | 'adventure'
  | 'quiet'
  | 'note'
  | 'documents'
  | 'stopover';

export type EntryFrontmatter = {
  day: number;
  title: string;
  location: string;
  kind: EntryKind;
  threads: string[];
  image: string | null;
};

const entries = defineCollection({
  loader: glob({ pattern: '*.md', base: '../../content/entries' }),
  schema: z
    .any()
    .superRefine((data, ctx) => {
      if (!validateEntry(data)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message:
            'frontmatter does not match content/schema/entry.schema.json — ' +
            ajv.errorsText(validateEntry.errors, { separator: '; ' }),
        });
      }
    })
    .transform((data) => data as EntryFrontmatter),
});

export const collections = { entries };
