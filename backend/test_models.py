import httpx, asyncio

async def t():
    # 先登录获取 token
    async with httpx.AsyncClient() as c:
        login = await c.post('http://localhost:8010/api/v1/auth/login', json={
            "email": "dev@example.com",
            "password": "demo123"
        })
        print("login:", login.status_code, login.json())
        token = login.json().get("data", {}).get("token")
        if not token:
            # 尝试其他默认账号
            login2 = await c.post('http://localhost:8010/api/v1/auth/login', json={
                "email": "admin@example.com",
                "password": "admin123"
            })
            print("login2:", login2.status_code, login2.json())
            token = login2.json().get("data", {}).get("token")

        headers = {"Authorization": f"Bearer {token}"} if token else {}

        r1 = await c.get('http://localhost:8010/api/v1/models/available', headers=headers)
        print("without force_refresh:", r1.json())

        r2 = await c.get('http://localhost:8010/api/v1/models/available?force_refresh=true', headers=headers)
        data = r2.json().get("data") or {}
        print("with force_refresh total:", data.get("total"))
        for m in data.get("items", []):
            print(f"  - {m['name']} ({m['model_id']}) status={m['status']}")

asyncio.run(t())