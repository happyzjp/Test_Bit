# KOKORO System

Distributed AI model training and inference system based on Bittensor subnet.

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 15+
- Redis (optional)
- CUDA 11.8+ (for GPU support)

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install the package in development mode (recommended)
pip install -e .
```

### Configuration

Create `.env` file in the root directory:

```env
DATABASE_URL=postgresql://kokoro:kokoro@localhost:5432/kokoro
REDIS_URL=redis://localhost:6379/0
BITNETWORK_NETUID=1
BITNETWORK_CHAIN_ENDPOINT=wss://entrypoint-finney.opentensor.ai:443
```

### Running Services

**Important**: Always run from the project root directory (`/Users/zjp/code/python/Kokoro-SN119/`), not from subdirectories.

#### Task Center

**⚠️ Important**: Task Center uses bittensor library which doesn't support uvloop. The code automatically uses asyncio loop.

**Option 1: Direct Python execution (Recommended)**
```bash
# From project root
python -m kokoro.task_center.task_center_main

# Or with custom host/port
TASK_CENTER_HOST=0.0.0.0 TASK_CENTER_PORT=8000 python -m kokoro.task_center.task_center_main
```

**Option 2: Using uvicorn with module path**
```bash
# From project root
# REQUIRED: --loop asyncio (bittensor doesn't support uvloop)
uvicorn kokoro.task_center.task_center_main:app --host 0.0.0.0 --port 8000 --loop asyncio
```

**Option 3: Set PYTHONPATH**
```bash
# From project root
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
cd kokoro/task_center
python task_center_main.py
```

#### Website Admin

```bash
# From project root
# Website admin doesn't use bittensor, so uvloop is fine
uvicorn kokoro.website_admin.main:app --host 0.0.0.0 --port 8001
```

#### Miner

```bash
# From project root
python -m kokoro.miner.miner_main
```

#### Validator

```bash
# From project root
python -m kokoro.validator.validator_main
```

## Project Structure

```
kokoro/
├── common/           # Common modules
├── website_admin/    # Website admin module
├── task_center/      # Task center module
├── miner/            # Miner module
└── validator/        # Validator module
```

## API Documentation

API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License

MIT

