# BCION Lite — verified commands (docs/ARCHITECTURE.md, CLAUDE.md)
# Substitutions per Lite Build Pack §10: pnpm scripts -> make targets.
#
# DEPLOY-18: this file is deliberately just an include shell. Every
# actual target lives in mk/*.mk, one file per concern, so a future task
# adds or extends a target there instead of re-editing this shared file
# (docs/DEVELOPMENT-PLAN.md's never-parallel groups list the root
# Makefile itself as exactly that kind of shared merge point).
include mk/*.mk
