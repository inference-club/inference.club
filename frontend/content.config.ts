import { defineContentConfig, defineCollection, z } from '@nuxt/content'

// Two collections: docs and blog. Keeping them separate gives each its own
// schema (blog needs publishedAt + author; docs needs sidebar order +
// category) and makes queries explicit.
export default defineContentConfig({
  collections: {
    docs: defineCollection({
      type: 'page',
      source: 'docs/**/*.md',
      schema: z.object({
        // Lower numbers sort first inside a category. Optional — defaults to
        // alphabetical fallback when missing.
        order: z.number().optional(),
        // Sidebar grouping. Pages without a category render at the top level.
        category: z.string().optional(),
      }),
    }),
    blog: defineCollection({
      type: 'page',
      source: 'blog/**/*.md',
      schema: z.object({
        publishedAt: z.string(),
        author: z.string().optional(),
        tags: z.array(z.string()).optional(),
      }),
    }),
  },
})
