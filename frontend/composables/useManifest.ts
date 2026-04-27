// Types and helpers for the service manifest — the YAML the agent
// uploads describing the operator's hosts, GPUs, and LLM services.
//
// See docs/plans/service-manifest.md in this repo for the full shape.

export interface ManifestModel {
  id: string
}

export interface ManifestService {
  name: string
  engine: string
  url: string
  models?: ManifestModel[]
  command?: string
  extra?: Record<string, string>
}

export interface ManifestGPU {
  vendor?: string
  model?: string
  vram_gb?: number
  count?: number
}

export interface ManifestHost {
  id: string
  hostname?: string
  address?: string
  notes?: string
  gpu?: ManifestGPU
  services?: ManifestService[]
}

export interface ParsedManifest {
  schema_version: number
  agent: { name: string; hostname?: string; listen_port?: number }
  hosts: ManifestHost[]
}

export interface PublicServiceManifest {
  schema_version: number
  parsed: ParsedManifest
  uploaded_at: string
  is_valid: boolean
}

export interface OwnerServiceManifest extends PublicServiceManifest {
  raw_yaml: string
  validation_errors: string[]
}

export interface ProfileProvider {
  id: number
  name: string
  is_active: boolean
  is_online: boolean
  registered_at: string | null
  last_seen_at: string | null
  manifest: PublicServiceManifest | null
  owner: string
  github_login: string | null
}

export interface PublicProfile {
  github_login: string
  name: string
  avatar_url: string
  github_url: string
  joined: string
  providers: ProfileProvider[]
}

// Engines the agent + server validators accept. Keep in sync with the
// validators on both sides.
export const ENGINE_LABELS: Record<string, string> = {
  vllm: 'vLLM',
  lmstudio: 'LM Studio',
  ollama: 'Ollama',
  sglang: 'SGLang',
  llamacpp: 'llama.cpp',
  tgi: 'TGI',
  other: 'Other',
}

export const VENDOR_LABELS: Record<string, string> = {
  nvidia: 'NVIDIA',
  amd: 'AMD',
  apple: 'Apple',
  intel: 'Intel',
}

export const useManifest = () => {
  const config = useRuntimeConfig()

  const fetchPublicProfile = (githubLogin: string) =>
    $fetch<PublicProfile>(
      `${config.public.apiBase}/api/users/${encodeURIComponent(githubLogin)}/`,
      { credentials: 'include' },
    )

  const fetchOwnerManifest = (providerId: number) =>
    $fetch<OwnerServiceManifest>(
      `${config.public.apiBase}/api/inference/providers/${providerId}/manifest/`,
      { credentials: 'include' },
    )

  return {
    fetchPublicProfile,
    fetchOwnerManifest,
  }
}
