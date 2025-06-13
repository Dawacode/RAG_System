## Setup

1.  **Navigate to Project Root:**
    Open your terminal and change the directory to the root of the project (the directory containing the `app` folder and `requirements.txt`). Let's assume this is `legal-rag/`.
    ```bash
    cd path/to/your/legal-rag/
    ```

2.  **Create and Activate Virtual Environment:**
    ```bash
    # Create virtual environment
    python -m venv .venv

    # Activate virtual environment
    # On Linux/macOS:
    source .venv/bin/activate
    # On Windows (Git Bash/PowerShell):
    # .venv\Scripts\activate
    ```
    You should see `(.venv)` prefixed to your terminal prompt.

3.  **Install Dependencies:**
    Ensure your `requirements.txt` file accurately reflects the working versions needed (especially `torch`, `unsloth`, `transformers`, `peft`, `accelerate`, `fastapi`, `uvicorn`, `supabase`, etc.).
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables (`.env` file):**
    Create a file named `.env` in the project root directory (`legal-rag/`). Add the necessary environment variables:
    ```dotenv
    # .env file content

    # Supabase Credentials
    SUPABASE_URL=YOUR_SUPABASE_PROJECT_URL
    SUPABASE_KEY=YOUR_SUPABASE_SERVICE_ROLE_OR_ANON_KEY

    # Path to the model checkpoint directory (MUST be correct)
    # This is used by app/utils/config.py
    MODEL_PATH=/path/to/your/model/checkpoint-XYZ

    # Optional: Uvicorn host/port/dev mode
    # HOST=0.0.0.0 # To make accessible on your network
    # PORT=8000
    # DEV_MODE=true # To enable reload when running 'python app/main.py' (not needed for 'uvicorn --reload')

    # Optional: Hugging Face Token (if base model requires it)
    # HF_TOKEN=your_huggingface_token
    ```
    *   Replace placeholders with your actual Supabase URL/Key and the correct **full path** to the directory containing your fine-tuned model files (like `adapter_config.json`, `config.json`, model weights).

## Running the FastAPI Server

The server is run using **Uvicorn**, an ASGI server. Since your application entry point is `app/main.py`, you need to run the command from the **project root directory** (`legal-rag/`).

```bash
# Ensure your virtual environment (.venv) is active
# Make sure you are in the project root directory (legal-rag/)

uvicorn app.main:app --reload
```

**Explanation:**

*   `uvicorn`: The command to start the server.
*   `app.main:app`: Specifies the location of the FastAPI application instance:
    *   `app`: Look inside the `app` directory/package.
    *   `.main`: Find the `main.py` file within `app`.
    *   `:app`: Use the variable named `app` (where `app = FastAPI()` is defined) inside `main.py`.
*   `--reload`: (For Development) Automatically restarts the server when code changes are detected. **Do not use `--reload` in production.**

**Expected Output:**

You should see logs indicating the server startup process:

```
INFO:     Will watch for changes in these directories: ['/path/to/your/legal-rag'] # Or similar
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using StatReload
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Creating FastAPI application instance (inside app/main.py)... # Log from main.py
INFO:     Included API router from app.api.routes.                 # Log from main.py
INFO:     Starting model loading process...                         # Log from generator.py
INFO:     Checkpoint Path: /path/to/your/model/checkpoint-XYZ      # Log from generator.py
... (Potentially many logs related to model loading - this can take time!) ...
INFO:     Generator model and tokenizer loaded and configured successfully. # Log from generator.py
INFO:     FastAPI application startup complete.                     # Log from main.py startup event
INFO:     Generator model confirmed loaded.                         # Log from main.py startup event
INFO:     Startup event processing took X.XX seconds.               # Log from main.py startup event
INFO:     Application startup complete.
```
If you see errors here, especially related to model loading, double-check your `MODEL_PATH` in `.env` and ensure all dependencies match the versions used during model saving.

## Sending a Query

Once the server is running, you can send queries to the `/api/v1/query` endpoint using an HTTP POST request. The request body should be JSON containing a `query` key.

**Example using `curl`:**

Open a *new* terminal window (or use an API client like Postman/Insomnia) and run the following command:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/query" \
-H "Content-Type: application/json" \
-d '{
    "query": "Jag köpte en villa för 8 månader sedan av en privatperson. Nu har jag upptäckt omfattande mögel i källaren som varken säljaren informerade om eller som kunde upptäckas vid en noggrann besiktning innan köpet. Vilka rättigheter har jag enligt Jordabalken? Kan jag kräva prisavdrag, skadestånd, eller till och med häva köpet?"
}'
```

**Explanation:**

*   `curl`: Command-line tool for making HTTP requests.
*   `-X POST`: Specifies the POST method.
*   `"http://127.0.0.1:8000/api/v1/query"`: The URL of the endpoint. Adjust the host/port if your server runs elsewhere.
*   `-H "Content-Type: application/json"`: Specifies that the request body contains JSON data.
*   `-d '{ ... }'`: Provides the JSON data payload. The key `query` holds the legal question string.

**Expected Response:**

If successful, the server will respond with a JSON object containing the generated answer:

```json
{
  "answer": "Baserat på informationen i Jordabalken, specifikt kapitel 4 § 19 om fel i fastighet, har du som köpare vissa rättigheter om ett dolt fel upptäcks... [Rest of the generated answer based on retrieved context and LLM generation] ...\n\nReferenser:\n[1] Jordabalken - 4 kap. § 19 (Källa: https://lagen.nu/1970:994#K4P19S1)\n[2] Jordabalken - 4 kap. § 12 (Källa: https://lagen.nu/1970:994#K4P12S1)\n[3] Jordabalken - 4 kap. § 19a (Källa: https://lagen.nu/1970:994#K4P19aS1)"
}
```
*(Note: The exact answer and references will vary depending on your retrieved documents and model generation.)*

If there's an error (e.g., model not loaded, retrieval failure), you might get a JSON error response like:
```json
{
  "detail": "Tjänsten är för närvarande otillgänglig på grund av ett internt fel i behandlingen."
}
```
or
```json
{
    "detail": "Ett oväntat internt serverfel inträffade."
}
```

## Stopping the Server

Go back to the terminal where Uvicorn is running and press `Ctrl+C`.

## Troubleshooting

*   **Model Loading Errors:** Check the `MODEL_PATH` in `.env`, ensure sufficient memory (CPU/GPU), and verify dependency versions match the environment used for saving the model checkpoint. Review logs in the `logs/` directory.
*   **Connection Errors:** Ensure the server is running and accessible (check host/port).
*   **Retrieval Errors:** Check Supabase credentials, connection, and the existence/permissions of the `match_legal_vectors` SQL function.
*   **`ModuleNotFoundError`:** Ensure you are running `uvicorn app.main:app --reload` from the project root directory (`legal-rag/`) and that your virtual environment is active.
*   **Other Errors:** Examine the FastAPI server logs and the logs in the `logs/` directory (`app_*.log`) for detailed tracebacks.
