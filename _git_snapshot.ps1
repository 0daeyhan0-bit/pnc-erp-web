# ============================================================
#  PNC ERP - git auto snapshot (scheduler runs this every 5 min)
#  Commits only when there are changes. Safety net vs multi-session overwrite loss.
#  Recover: git -C <root> log --oneline  /  git -C <root> checkout <commit> -- <file>
#  NOTE: uses $PSScriptRoot (no hardcoded Korean path) so encoding never breaks it.
# ============================================================
$ErrorActionPreference = 'SilentlyContinue'
$git  = "C:\Program Files\Git\cmd\git.exe"
$root = $PSScriptRoot

& $git -C $root add -A
& $git -C $root diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    $msg = "auto snapshot " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    & $git -C $root commit -m $msg | Out-Null
    ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + "  committed") | Add-Content "$root\_git_snapshot.log"
}
