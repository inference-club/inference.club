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
        // Header image path (e.g. /images/blog/<slug>.png). Optional — pages
        // fall back to a gradient when absent.
        image: z.string().optional(),
        // Text prompt used to generate the header image. Every post should
        // include this so a matching banner can be (re)generated on demand.
        image_prompt: z.string().optional(),
        // Mark one post to surface on the homepage. Newest featured wins;
        // falls back to the newest post overall when none is flagged.
        featured: z.boolean().optional(),
      }),
    }),
  },
})
