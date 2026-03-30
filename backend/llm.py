import os


def get_llm(provider, model, api_key):
    if provider == "Groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, api_key=api_key, temperature=0)

    elif provider == "Google Gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, api_key=api_key, temperature=0)

    elif provider == "Anthropic Claude":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=api_key, temperature=0)

    else:
        raise ValueError(f"Unsupported provider: {provider}")