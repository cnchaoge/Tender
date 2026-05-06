import urllib.request, json
req = urllib.request.Request(
    'http://localhost:8000/api/auth/login',
    data=json.dumps({'username': 'admin', 'password': 'admin123'}).encode(),
    headers={'Content-Type': 'application/json'}
)
r = urllib.request.urlopen(req)
print(r.read().decode())
