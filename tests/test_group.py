import requests
import json

url = "http://localhost:5001/api/duplicates/analyze-album/test"
response = requests.post(url, json={"threshold": 0.90}, stream=True)

for line in response.iter_lines():
    if line:
        line_str = line.decode('utf-8')
        if line_str.startswith('data:'):
            data = json.loads(line_str[5:])

            if data['event'] == 'complete':
                print("\n🎉 RÉSULTATS:")
                groups = data['data']['groups']
                print(f"Nombre de groupes trouvés: {len(groups)}")

                for group in groups:
                    print(f"\n📁 Groupe {group['group_id']} (similarité moy: {group['$                    for img in group['images']:
                        primary = " ⭐" if img['is_primary'] else ""
                        print(f"   - {img['filename']} ({img['similarity']:.1%}){prim$

            elif data['event'] == 'error':
                print(f"❌ Erreur: {data['data']['error']}")

            elif data['event'] == 'progress':
                print(f"⏳ {data['data']['details']} - {data['data']['progress']}%")   

