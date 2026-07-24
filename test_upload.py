import requests

url = 'http://localhost:8001/runs/upload-csv'
files = {'file': open('test.csv', 'rb')}
r = requests.post(url, files=files)
print(r.status_code)
print(r.text)
