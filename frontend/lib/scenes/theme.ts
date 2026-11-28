// One palette for every scene. At night the ground is a deep blue-black and
// everything that matters is a bright, saturated light; lights add up where
// they cross. In the light theme the same drawing is made in strong inks on
// warm white paper. The generated artwork on the homepage is deliberately in
// every style going, so the scenes carry the page's colour on their own.

export interface Palette {
  /** Panel background (also used by SceneStage for its CSS background). */
  ground: string
  /** Primary marks: people, outlines, anything neutral. */
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
  pink: string
  lime: string
  /** Lights add up on a dark ground; ink does not on paper. */
  additive: boolean
}

export const NIGHT: Palette = {
  ground: '#070a1c',
  ink: '#f3f5ff',
  dim: '#8c97d6',
  line: '#283070',
  amber: '#ffb52e',
  coral: '#ff5a6e',
  violet: '#a487ff',
  teal: '#27e3c4',
  sky: '#45bfff',
  pink: '#ff66d4',
  lime: '#b4f04a',
  additive: true,
}

export const PAPER: Palette = {
  ground: '#fbf8f1',
  ink: '#171b3d',
  dim: '#6c7397',
  line: '#ded7c7',
  amber: '#e58a00',
  coral: '#e2334d',
  violet: '#6843ee',
  teal: '#009a80',
  sky: '#0c84d8',
  pink: '#d4219c',
  lime: '#5c9a00',
  additive: false,
}

export const paletteFor = (dark: boolean): Palette => (dark ? NIGHT : PAPER)

/** The kinds of thing the club makes, each with a fixed colour role. */
export type Signal = 'text' | 'image' | 'speech' | 'music' | 'video' | 'shape'
export const SIGNALS: Signal[] = ['text', 'image', 'speech', 'music', 'video', 'shape']
export const signalColor = (p: Palette, s: Signal): string =>
  ({ text: p.sky, image: p.amber, speech: p.teal, music: p.violet, video: p.coral, shape: p.pink })[s]

/** Who and what appears in the scenes; keep these meanings in new scenes. */
export const roleColor = (p: Palette, r: 'person' | 'agent' | 'machine' | 'private'): string =>
  ({ person: p.ink, agent: p.lime, machine: p.amber, private: p.violet })[r]
