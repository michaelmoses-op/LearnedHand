"""Print the OpenAPI schema without starting a server: python -m app.core.openapi_dump"""

import json

from app.main import create_app

if __name__ == "__main__":
    print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))
