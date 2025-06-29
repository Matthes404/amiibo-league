# Amiibo League

This project is a Flask web application that uses SQLite for storing data. Follow these steps to run it locally:

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the Application**
   ```bash
   python app.py
   ```
   The app will start in debug mode and listen on `localhost:5000`.

3. **Access in Browser**
   Open your web browser and navigate to `http://localhost:5000` to use the application.

The database file `amiibo.db` is created automatically on first run. All persistent state is stored in this file.
