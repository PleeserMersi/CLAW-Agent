# Environment Variables Reference

Complete reference for all environment variables in CLAW-Agent.

---

## Required Variables

### JLAB_USERNAME
- **Type**: String
- **Required**: Yes
- **Description**: Jefferson Lab logbook API username
- **Example**: `jblank`

### JLAB_PASSWORD
- **Type**: String
- **Required**: Yes
- **Description**: Jefferson Lab logbook API password
- **Example**: `secure_password`

---

## Optional Variables

### LOG_LEVEL
- **Type**: String
- **Default**: `INFO`
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- **Description**: Logging verbosity

### OPENCLAW_PATH
- **Type**: String
- **Default**: (empty)
- **Description**: Path to OpenClaw installation directory. If set, the project uses `openclaw` CLI via `<OPENCLAW_PATH>/bin/openclaw`. If **not set or empty**, the project uses **vLLM API directly** instead.
- **Example**: `/home/user/.npm-global/lib/node_modules/openclaw`

### AGENT_NAME
- **Type**: String
- **Required**: Yes
- **Description**: OpenClaw agent name for LLM calls
- **Default**: `fault_analyst`

### VLLM_BASE_URL
- **Type**: URL
- **Default**: `http://localhost:8000`
- **Description**: vLLM API endpoint URL (used when `OPENCLAW_PATH` is not set)
- **Example**: `http://localhost:8000` or `http://192.168.1.100:8000`

### VLLM_MODEL_NAME
- **Type**: String
- **Default**: `qwen3-32b-local`
- **Description**: Model name to use for vLLM inference (used when `OPENCLAW_PATH` is not set)
- **Example**: `qwen3-122b-a10b`, `llama3-70b`, `mistral-large`

### VLLM_API_KEY
- **Type**: String
- **Default**: (empty)
- **Description**: API key for vLLM endpoint if authentication is required (used when `OPENCLAW_PATH` is not set)
- **Example**: `sk-xxx`

### OPENCLAW_CMD
- **Type**: String
- **Default**: (auto-set based on `OPENCLAW_PATH`)
- **Description**: OpenClaw command path. Automatically set to `<OPENCLAW_PATH>/bin/openclaw` if `OPENCLAW_PATH` is set, otherwise `None`.
- **Note**: When `OPENCLAW_PATH` is not set, this is `None` and the project uses vLLM API directly.

---

## SSH Tunnel Variables

### SSH_USERNAME
- **Type**: String
- **Required for remote**: Yes
- **Description**: SSH username
- **Example**: `blankenship`

### SSH_HOST
- **Type**: String
- **Required for remote**: Yes
- **Description**: SSH server address
- **Example**: `137.155.253.88`

### SSH_TUNNEL_N_LOCAL
- **Type**: Integer
- **Required if using tunnels**: Yes
- **Description**: Local port for tunnel N
- **Example**: `SSH_TUNNEL_1_LOCAL=8000`

### SSH_TUNNEL_N_REMOTE
- **Type**: Integer
- **Required if using tunnels**: Yes
- **Description**: Remote port for tunnel N
- **Example**: `SSH_TUNNEL_1_REMOTE=8001`

---

## Dashboard Server Variables

### DASHBOARD_SSH_USERNAME
- **Type**: String
- **Description**: SSH username for dashboard server
- **Example**: `blankenship`

### DASHBOARD_SSH_HOST
- **Type**: String
- **Description**: SSH host for dashboard server
- **Example**: `137.155.253.88`

### DASHBOARD_SSH_PORT
- **Type**: Integer
- **Default**: `22`
- **Description**: SSH port for dashboard server

### DASHBOARD_REMOTE_PORT
- **Type**: Integer
- **Default**: `3335`
- **Description**: Remote port for dashboard service

---

## Example .env Files

### Minimal (Local Testing)
```bash
JLAB_USERNAME=test_user
JLAB_PASSWORD=test_password
AGENT_NAME=test_agent
LOG_LEVEL=DEBUG
```

### Production (Remote Access)
```bash
JLAB_USERNAME=prod_user
JLAB_PASSWORD=secure_password
AGENT_NAME=fault_analyst
LOG_LEVEL=INFO

SSH_USERNAME=prod_ssh_user
SSH_HOST=137.155.253.88
SSH_TUNNEL_1_LOCAL=8000
SSH_TUNNEL_1_REMOTE=8001
SSH_TUNNEL_2_LOCAL=11435
SSH_TUNNEL_2_REMOTE=11434

DASHBOARD_SSH_USERNAME=prod_ssh_user
DASHBOARD_SSH_HOST=137.155.253.88
DASHBOARD_SSH_PORT=22
DASHBOARD_REMOTE_PORT=3335
```

---

## Security Best Practices

1. **Never commit `.env`** to version control
2. **Use strong passwords** for JLab API
3. **Rotate credentials** periodically
4. **Set file permissions**: `chmod 600 .env`
5. **Use environment variables** in production

---

## Related Documentation

- [Configuration](./CONFIGURATION.md) - Full configuration guide
- [Installation](./INSTALLATION.md) - Setup instructions

---

*For configuration details, see [CONFIGURATION.md](./CONFIGURATION.md).*