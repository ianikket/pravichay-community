"""Run the community app locally: python app.py."""

import os

from community import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "5051")), debug=False)
