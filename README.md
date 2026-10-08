# BoligPortal application agent

Turns BoligPortal SearchAgent alert emails into tailored application drafts on Telegram. You copy the draft, open the listing in the BoligPortal app, and paste it into "Kontakt".

```
SearchAgent email → mailbox folder "BoligPortal"
cron-job.org (every 3 min) → GitHub Actions → main.py
  read unread alerts (IMAP) → OpenAI (gpt-6-luna) extracts listings → filters.py (config.yaml)
  → OpenAI checks requirements + drafts message → Telegram card → email marked read
```

The agent never visits boligportal.dk. BoligPortal forbids automated access, and its Cloudflare protection blocks GitHub's servers.

## Search criteria (`config.yaml`)
| | Solo | Shared |
|---|---|---|
| Rooms | 2 værelser | 3+ værelser |
| Rent + aconto | ≤ 14,000 | ≤ 19,000 |
| Area | København K, V, Ø, N, NV | same |
| Lease | unlimited or ≥ 24 months | same |
| Move-in | 1 Dec 2026 – 31 Jan 2027 | same |

Missing information never rejects a listing. It shows up as ❔ on the card.

## Setup

1. **BoligPortal**: complete your tenant profile, then create one SearchAgent: areas København K, V, Ø, N and NV, 2+ rooms, max rent 19,000. The agent decides per listing whether it fits solo or shared.
2. **Mailbox**: add a filter that moves BoligPortal alert emails into a folder/label called `BoligPortal`, and create an app password (Gmail: Google Account → Security → App passwords; IMAP must be enabled).
3. **Telegram**: create a bot with @BotFather and copy the token. Send the bot any message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
4. **OpenAI API key** from platform.openai.com (API credit is billed separately from a ChatGPT subscription).
5. **Applicant profile**: plain-text facts about you (and your friend, for shared applications): name, age, job/studies, income, non-smoker, pets, why these areas, references, contact availability. Drafts only use facts from this text.
6. **GitHub secrets** (repo → Settings → Secrets and variables → Actions):

   | Secret | Value |
   |---|---|
   | `IMAP_HOST` | e.g. `imap.gmail.com` (default if empty) |
   | `IMAP_USER` | your email address |
   | `IMAP_PASSWORD` | the app password |
   | `IMAP_FOLDER` | optional, default `BoligPortal` |
   | `OPENAI_API_KEY` | API key |
   | `TELEGRAM_BOT_TOKEN` | bot token |
   | `TELEGRAM_CHAT_ID` | chat id |
   | `APPLICANT_PROFILE` | the profile text from step 5 |

7. **Test**: Actions tab → boligportal-agent → Run workflow.
8. **cron-job.org trigger**:
   - Create a fine-grained token at github.com/settings/personal-access-tokens: only this repository, permission **Actions: Read and write**, 1-year expiry.
   - On cron-job.org, create a job:
     - URL: `https://api.github.com/repos/annabzinkowska/boligportal-agent/actions/workflows/agent.yml/dispatches`
     - Schedule: every 3 minutes
     - Advanced → Request method: `POST`
     - Headers:
       - `Authorization: Bearer <token>`
       - `Accept: application/vnd.github+json`
       - `X-GitHub-Api-Version: 2022-11-28`
     - Body: `{"ref":"main"}`
   - Click "Test run". It should return HTTP 204, and a new run should appear in the Actions tab.
   - Turn on failure notifications.

The repo is public so Actions minutes are free. All personal data is stored in secrets, and logs only show listing IDs.

## Local testing
```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest
set -a; . ./.env; set +a           # OPENAI_API_KEY=...; plus applicant_profile.md (gitignored)
.venv/bin/python main.py --eml alert.eml   # save a real alert email as .eml; prints the cards
```

Once real alert emails arrive, check the drafts with `--eml` and tune `prompt.md`.
