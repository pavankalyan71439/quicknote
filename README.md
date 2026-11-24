# QuickNote

QuickNote is a small Flask app for creating an account and saving, editing, and deleting personal notes. Notes are stored in a local SQLite database.

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Set a strong session secret before starting the app:
   - PowerShell: `$env:SECRET_KEY = "your-long-random-secret"`
   - macOS/Linux: `export SECRET_KEY="your-long-random-secret"`
4. Start the app with `python app.py`.
5. Open `http://127.0.0.1:5000`.

The app creates `quicknotes.db` in its working directory on first run. The database is ignored by Git and should not be committed.
