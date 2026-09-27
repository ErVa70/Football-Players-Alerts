import requests

headers = {
    "User-Agent": "Mozilla/5.0"
}


def search_country(country_name):
    url = "https://www.fotmob.com/api/data/search/suggest"

    response = requests.get(
        url,
        params={
            "term": country_name,
            "hits": 10,
            "lang": "en"
        },
        headers=headers,
        timeout=20
    )

    response.raise_for_status()

    return response.json()


for country in ["Uruguay", "France"]:

    print("=" * 60)
    print(f"SEARCHING FOR: {country}")
    print("=" * 60)

    results = search_country(country)

    for group in results:

        print(
            f"\nGroup: "
            f"{group.get('title', {}).get('value')}"
        )

        for suggestion in group.get("suggestions", []):

            print(
                f"  type={suggestion.get('type')} | "
                f"id={suggestion.get('id')} | "
                f"name={suggestion.get('name')} | "
                f"teamId={suggestion.get('teamId')} | "
                f"teamName={suggestion.get('teamName')}"
            )

    print()
