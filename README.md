# ForeGuard

ForeGuard is a local command-safety prototype for AI-assisted Linux workflows. It labels proposed commands **ALLOW**, **REVIEW**, or **BLOCK** without executing them. It is not yet ready to enforce real command execution.

## Try it

Run `python -m app.classifier`, type a command, press Enter, then Ctrl+D. The program prints a JSON assessment.

## Test it

Run `python -m unittest discover -s tests`.
