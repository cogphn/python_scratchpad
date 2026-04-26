from openai import OpenAI

def main():
    client = OpenAI(base_url="http://10.30.23.104:1234/v1", api_key="lm-studio")

    completion = client.chat.completions.create(
    model="google/gemma-4-e2b",
    messages=[
        {"role": "system", "content": "You are a consultant. You always fact-check your responses. You are concise and factual"},
        {"role": "user", "content": "summarize the book paradise lost one paragraph. Generate three unique responses."}
    ],
    temperature=0.1,
    )

    print(completion.choices[0].message.content)

if __name__ == "__main__":
    main()
#
