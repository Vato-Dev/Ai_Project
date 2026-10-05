# Working project starter

This baseline already runs in mock mode. Copy this entire directory into your own repository; work from its root. Create and activate a Python virtual environment, run `python -m pip install -r requirements-dev.txt` and `python -m pip install --no-deps -e .`, then copy `.env.example` to `.env`. Run `python -m pytest`.

Start the API with `python -m uvicorn ticket_app.api:create_app --factory --host 127.0.0.1 --port 8000` and run `python -m streamlit run ui/app.py` in another terminal. Open http://localhost:8501 and http://localhost:8000/docs. The generic mock analyzes a request, stores the validated result and requires human review. The original I1 summary CLI is also preserved.

Your assigned brief describes the extension tasks: scenario policy and prompt, local analysis adapter, feature tests, Jenkins pipeline, Dockerfile and local Terraform resources. The local adapter and delivery files are deliberately incomplete. Obtain your prepared Jenkins agent from the instructor. Use the assigned README template as your final README.
