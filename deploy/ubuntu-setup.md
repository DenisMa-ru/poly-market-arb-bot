# Ubuntu setup

## 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

## 2. Clone repository

```bash
git clone <your-repo-url> /opt/poly-market-arb-bot
cd /opt/poly-market-arb-bot
```

## 3. Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]
cp .env.example .env
```

Fill `.env` before starting the bot.

## 4. Manual run

```bash
source .venv/bin/activate
python scripts/paper_run.py
```

In another shell:

```bash
source .venv/bin/activate
streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8501
```

## 5. systemd services

Copy service files:

```bash
sudo cp deploy/systemd/poly-market-arb-bot.service /etc/systemd/system/
sudo cp deploy/systemd/poly-market-arb-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable poly-market-arb-bot.service
sudo systemctl enable poly-market-arb-dashboard.service
sudo systemctl start poly-market-arb-bot.service
sudo systemctl start poly-market-arb-dashboard.service
```

Check status:

```bash
sudo systemctl status poly-market-arb-bot.service
sudo systemctl status poly-market-arb-dashboard.service
```

