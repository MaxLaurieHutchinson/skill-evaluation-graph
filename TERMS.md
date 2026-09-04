# Terms of Service for Skill Evaluation Graph (SEG)

*Last updated: September 4, 2026*

Welcome to the **Skill Evaluation Graph (SEG)** repository (`MaxLaurieHutchinson/skill-evaluation-graph`). By installing, executing, or integrating SEG into your projects, harnesses, or CI pipelines, you agree to the following terms:

## 1. License & Permitted Use
SEG is licensed under the terms of the **MIT License**. You are free to use, modify, distribute, integrate, and commercially leverage SEG subject to the copyright notice and disclaimers set forth in [`LICENSE`](LICENSE).

## 2. Disclaimer of Warranty
SEG is provided "AS IS", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and noninfringement. In no event shall the authors or copyright holders be liable for any claim, damages, or other liability arising from the use of this software.

## 3. Autonomous Execution & Agent Safety
SEG provides bounded autonomous repair loops (`scripts/run_loop.py`) designed to propose and apply structural patches to Agent Skills. While SEG implements Git rollback locks and safety bounds, users are solely responsible for reviewing changes, maintaining source control backups, and governing agent tool permissions in production environments.

## 4. Third-Party Harnesses & Platforms
SEG provides compatibility adapters for third-party platforms including OpenAI Codex, Anthropic Claude Code, and Google Antigravity. SEG is an independent open-source project and is not officially affiliated with or endorsed by Anthropic, OpenAI, or Google.

## 5. Contact
For support, feedback, or contribution inquiries, please use the issue tracker:
[https://github.com/MaxLaurieHutchinson/skill-evaluation-graph/issues](https://github.com/MaxLaurieHutchinson/skill-evaluation-graph/issues)
