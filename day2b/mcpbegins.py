import os
from dotenv import load_dotenv
import asyncio
from google import genai
from google.genai import types

import uuid

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from google.adk.apps.app import App, ResumabilityConfig
from google.adk.tools.function_tool import FunctionTool
from google.adk.runners import InMemoryRunner

from IPython.display import display, Image as IPImage
import base64
import subprocess


load_dotenv()
client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

retry_config = types.HttpRetryOptions(
    attempts=5,  # Maximum retry attempts
    exp_base=7,  # Delay multiplier
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],  # Retry on these HTTP errors
)

# MCP integration with Everything Server
mcp_image_server = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",  # Run MCP server via npx
            args=[
                "-y",  # Argument for npx to auto-confirm install
                "@modelcontextprotocol/server-everything",
            ],
            tool_filter=["getTinyImage"],
        ),
        timeout=30,
    )
)

# Create image agent with MCP integration
image_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    name="image_agent",
    instruction="Use the MCP Tool to generate images for user queries",
    tools=[mcp_image_server],
)

# Provide a sample tiny image
if __name__ == "__main__":
    question = input("Ask your agent something: ")
    runner = InMemoryRunner(agent=image_agent)

    async def main():
        response = await runner.run_debug(question, verbose=True)
        for event in response:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "function_response") and part.function_response:
                        for item in part.function_response.response.get("content", []):
                            if item.get("type") == "image":
                                image_bytes = base64.b64decode(item["data"])
                                output_path = "output.png"
                                with open(output_path, "wb") as f:
                                    f.write(image_bytes)
                                print(f"✅ Image saved to {output_path}")
                                subprocess.run(["open", output_path])

    asyncio.run(main())