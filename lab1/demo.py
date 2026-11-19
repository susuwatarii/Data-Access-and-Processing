import requests


def main():
    url = "http://127.0.0.1:8000/api/items"

    response = requests.get(url, timeout=10)

    print(response.status_code)
    print(response.json())
    print("hello")


if __name__ == "__main__":
    main()
