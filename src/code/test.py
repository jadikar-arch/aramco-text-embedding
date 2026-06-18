from openai import OpenAI

client = OpenAI(
    api_key="rpa_WS75SLX6RXIW02JKC4VGEUDWNVVYNRJWJAQ95VAQ1t6h5p",
    base_url="https://api.runpod.ai/v2/xw4gpf7mdcmrl4/openai/v1"
)
print(client.models.list())