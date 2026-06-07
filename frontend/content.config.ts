import { defineContentConfig, defineCollection, z } from '@nuxt/content'

// One collection per locale per content type (blog_en, blog_fr, docs_en, …).
// Nuxt Content v3 has no built-in i18n, so this is the official pattern: each
// collection sources a language subfolder. Nuxt strips the static base of the
// `include` glob (e.g. `en/blog`), so we set `prefix` to re-add the content-type
// segment — stored paths stay locale-free but type-prefixed (/blog/x, /docs/x),
// which is what the blog/docs pages query. (A `prefix: ''` would collapse posts
// to /x and 404 every page.) The active locale is chosen at query time, falling
// back to English when a translation is missing (see
// composables/useLocalizedContent.ts).
//
// Adding a language = add its code here (and one content/<code>/ folder).
const LOCALES = ['en', 'zh', 'ja', 'ru', 'fr', 'ko', 'es'] as const

// blog needs publishedAt + author; docs needs sidebar order + category.
const blogSchema = z.object({
  publishedAt: z.string(),
  author: z.string().optional(),
  tags: z.array(z.string()).optional(),
  // Header image path (e.g. /images/blog/<slug>.png). Optional — pages fall
  // back to a gradient when absent.
  image: z.string().optional(),
  // Text prompt used to generate the header image.
  image_prompt: z.string().optional(),
  // Mark one post to surface on the homepage.
  featured: z.boolean().optional(),
})

const docsSchema = z.object({
  // Lower numbers sort first inside a category.
  order: z.number().optional(),
  // Sidebar grouping. Pages without a category render at the top level.
  category: z.string().optional(),
})

const collections: Record<string, ReturnType<typeof defineCollection>> = {}
for (const code of LOCALES) {
  collections[`blog_${code}`] = defineCollection({
    type: 'page',
    source: { include: `${code}/blog/**/*.md`, prefix: '/blog' },
    schema: blogSchema,
  })
  collections[`docs_${code}`] = defineCollection({
    type: 'page',
    source: { include: `${code}/docs/**/*.md`, prefix: '/docs' },
    schema: docsSchema,
  })
}

export default defineContentConfig({ collections })
