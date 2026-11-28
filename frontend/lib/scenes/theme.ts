// One palette for every scene: "porch lights". Night is deep indigo and the
// things that matter are small warm lights; in the light theme the same
// drawing is printed in indigo ink on cream paper. The generated artwork on
// the homepage uses the same four colours (see scripts/showcase/showcase.json).

export interface Palette {
  /** Panel background (also used by SceneStage for its CSS background). */
  ground: string
  /** Primary marks: text-like things, people, outlines. */
  ink: string
  /** Secondary marks. */
  dim: string
  /** Hairlines and resting links. */
  line: string
  amber: string
  coral: string
  violet: string
  teal: string
  sky: string
  /** Lights add up on a dark ground; ink does not on paper. */
  additive: boolean
}

export const NIGHT: Palette = {
  ground: '#0c1230',
  ink: '#fff3d6',
  dim: '#8b93c7',
  line: '#343d7a',
  amber: '#ffb44a',
  coral: '#ff7a66',
  violet: '#a99bff',
  teal: '#6fd6c9',
  sky: '#86b6ff',
  additive: true,
}

export const PAPER: Palette = {
  ground: '#f6efe1',
  ink: '#1b2350',
  dim: '#6b7299',
  line: '#cfc6ae',
  amber: '#d9831f',
  coral: '#d9523f',
  violet: '#6a5ae0',
  teal: '#17897c',
  sky: '#3a76d6',
  additive: false,
}

export const paletteFor = (dark: boolean): Palette => (dark ? NIGHT : PAPER)

/** The kinds of thing the club makes, each with a fixed colour role. */
export type Signal = 'text' | 'image' | 'speech' | 'music' | 'video' | 'shape'
export const SIGNALS: Signal[] = ['text', 'image', 'speech', 'music', 'video', 'shape']
export const signalColor = (p: Palette, s: Signal): string =>
  ({ text: p.ink, image: p.amber, speech: p.teal, music: p.violet, video: p.coral, shape: p.sky })[s]
