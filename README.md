# BoligPortal application agent

Turns BoligPortal SearchAgent alert emails into tailored application drafts, emailed back to the same inbox. You copy the draft, open the listing in the BoligPortal app, and paste it into "Kontakt".

```
SearchAgent email → mailbox folder "BoligPortal"
cron-job.org (every 3 min) → GitHub Actions → main.py
  read unread alerts (IMAP) → OpenAI (gpt-6-luna) extracts listings → filters.py (config.yaml)
  → OpenAI checks requirements + drafts message → draft email (sent via Gmail SMTP) → alert marked read
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
2. **Mailbox**: create an app password (Gmail: myaccount.google.com/apppasswords). Once the first alert arrives, use "Filter messages like these" on it: match the BoligPortal **sender** plus a subject word only alerts use, then Skip the Inbox + label `BoligPortal`. Don't filter on the word "boligportal" alone: it would also catch landlord-reply notifications and the agent's own draft emails.
3. **Draft emails** are sent from the same Gmail account to itself (or to `NOTIFY_TO`), using the app password.
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
   | `NOTIFY_TO` | optional, where drafts go (default: `IMAP_USER`) |
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
