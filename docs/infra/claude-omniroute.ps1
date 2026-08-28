# claude-omniroute.ps1
# Launch a Claude Code session routed through OmniRoute (local gateway) instead of
# api.anthropic.com. REVERSIBLE and ISOLATED: it only sets environment variables for
# the process it starts. It does NOT modify settings.json, the OAuth credentials, or any
# global config. Your normal Claude Code (desktop app / default launch) is unaffected.
#
# Usage:   powershell -ExecutionPolicy Bypass -File claude-omniroute.ps1  [-- <claude args>]
# Stop routing: just close this session and use Claude Code normally.

$ErrorActionPreference = "Stop"

# --- 1. OmniRoute endpoint (Anthropic-compatible surface) ---
$OmniBase = "http://127.0.0.1:20128"   # Claude Code appends /v1/messages

# --- 2. Preflight: is OmniRoute up? ---
$code = & curl.exe -s -m 5 -o NUL -w "%{http_code}" "$OmniBase/v1/models" 2>$null
if ($code -ne "200") {
    Write-Host "OmniRoute is not responding on $OmniBase (got '$code'). Start it with: omniroute serve" -ForegroundColor Red
    exit 1
}
Write-Host "OmniRoute reachable on $OmniBase (HTTP $code)" -ForegroundColor Green

# --- 3. Locate the newest Claude Code binary ---
$ccRoot = Join-Path $env:APPDATA "Claude\claude-code"
$ccExe = Get-ChildItem $ccRoot -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending |
    ForEach-Object { Join-Path $_.FullName "claude.exe" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
if (-not $ccExe) {
    Write-Host "Could not find claude.exe under $ccRoot" -ForegroundColor Red
    exit 1
}
Write-Host "Using Claude Code: $ccExe" -ForegroundColor Green

# --- 4. Point THIS process at OmniRoute (env-only, not persisted) ---
$env:ANTHROPIC_BASE_URL = $OmniBase
# Dummy bearer: OmniRoute accepts localhost calls without a real key; Claude Code just
# needs a token set so it does not fall back to the Anthropic OAuth flow.
$env:ANTHROPIC_AUTH_TOKEN = "sk-omniroute-local"
# Claude Code sends bare claude-* model ids, which OmniRoute reports as "ambiguous".
# Force the auto router instead (OmniRoute picks a connected provider + does fallback).
# Alternative combos: auto/best-coding (main), auto/best-fast (small).
$env:ANTHROPIC_MODEL = "auto"
$env:ANTHROPIC_SMALL_FAST_MODEL = "auto"
# "auto" is not a model id Claude Code knows, so it warns about the assumed context
# window. This silences that cosmetic warning (the router still works either way).
$env:CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT = "1"

Write-Host "Routing: Claude Code -> OmniRoute -> connected provider (model=auto)" -ForegroundColor Cyan
Write-Host "Your global config / OAuth are untouched. Close this window to stop." -ForegroundColor DarkGray
Write-Host ""

# --- 5. Launch Claude Code (pass through any extra args after --) ---
& $ccExe @args
