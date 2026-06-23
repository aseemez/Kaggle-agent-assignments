import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])


model = genai.GenerativeModel("gemini-2.5-flash")
response = model.generate_content("Say hello in one word.")
print(response.text)
