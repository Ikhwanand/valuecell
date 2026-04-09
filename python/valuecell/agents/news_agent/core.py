"""News Agent Core Implementation."""

import os
from typing import Any, AsyncGenerator, Dict, Optional

from agno.agent import Agent
from agno.tools.baidusearch import BaiduSearchTools
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.webbrowser import WebBrowserTools
from agno.tools.hackernews import HackerNewsTools
from agno.tools.newspaper4k import Newspaper4kTools
from agno.tools.googlesearch import GoogleSearchTools
from loguru import logger

from valuecell.adapters.models import create_model_for_agent
from valuecell.config.manager import get_config_manager
from valuecell.core.agent.responses import streaming
from valuecell.core.types import BaseAgent, StreamResponse

from .prompts import NEWS_AGENT_INSTRUCTIONS
from .tools import get_breaking_news, get_financial_news, web_search


def _get_web_search_tool() -> list:
    """
    Return the appropriate web search tools based on configured API keys.

    - If GOOGLE_API_KEY is set     → custom web_search using Gemini grounding
    - If OPENROUTER_API_KEY is set → custom web_search using Perplexity via OpenRouter
    - Otherwise                    → Agno built-in tools (DuckDuckGo + BaiduSearch + WebBrowser)
    """
    has_google = bool(os.getenv("GOOGLE_API_KEY"))
    has_openrouter = bool(os.getenv("OPENROUTER_API_KEY"))

    if has_google or has_openrouter:
        logger.info("NewsAgent web search: using custom provider (Google/OpenRouter)")
        return [web_search]
    else:
        logger.info("NewsAgent web search: using Agno built-in tools (DuckDuckGo + BaiduSearch + WebBrowser)")
        return [GoogleSearchTools(), DuckDuckGoTools(), BaiduSearchTools(), WebBrowserTools(), HackerNewsTools(), Newspaper4kTools()]


class NewsAgent(BaseAgent):
    """News Agent for fetching and analyzing news."""

    def __init__(self, **kwargs):
        """Initialize the News Agent."""
        super().__init__(**kwargs)
        # Load agent configuration
        self.config_manager = get_config_manager()
        self.agent_config = self.config_manager.get_agent_config("news_agent")

        # Load tools based on configuration
        web_search_tools = _get_web_search_tool()
        available_tools = [
            *web_search_tools,
            get_breaking_news,
            get_financial_news,
        ]

        # Use create_model_for_agent to load agent-specific configuration
        self.knowledge_news_agent = Agent(
            model=create_model_for_agent("news_agent"),
            tools=available_tools,
            instructions=NEWS_AGENT_INSTRUCTIONS,
        )

        logger.info("NewsAgent initialized with news tools")

    async def stream(
        self,
        query: str,
        conversation_id: str,
        task_id: str,
        dependencies: Optional[Dict] = None,
    ) -> AsyncGenerator[StreamResponse, None]:
        """Stream news responses."""
        logger.info(
            f"Processing news query: {query[:100]}{'...' if len(query) > 100 else ''}"
        )

        try:
            response_stream = self.knowledge_news_agent.arun(
                query,
                stream=True,
                stream_intermediate_steps=True,
                session_id=conversation_id,
            )
            async for event in response_stream:
                if event.event == "RunContent":
                    yield streaming.message_chunk(event.content)
                elif event.event == "ToolCallStarted":
                    yield streaming.tool_call_started(
                        event.tool.tool_call_id, event.tool.tool_name
                    )
                elif event.event == "ToolCallCompleted":
                    yield streaming.tool_call_completed(
                        event.tool.result, event.tool.tool_call_id, event.tool.tool_name
                    )

            yield streaming.done()
            logger.info("News query processed successfully")

        except Exception as e:
            logger.error(f"Error processing news query: {str(e)}")
            logger.exception("Full error details:")
            yield {"type": "error", "content": f"Error processing news query: {str(e)}"}

    async def run(self, query: str, **kwargs) -> str:
        """Run news agent and return response."""
        logger.info(
            f"Running news agent with query: {query[:100]}{'...' if len(query) > 100 else ''}"
        )

        try:
            logger.debug("Starting news agent processing")

            # Get the complete response from the knowledge news agent
            response = await self.knowledge_news_agent.arun(query)

            logger.info("News agent query completed successfully")
            logger.debug(f"Response length: {len(str(response.content))} characters")

            return response.content

        except Exception as e:
            logger.error(f"Error in NewsAgent run: {e}")
            logger.exception("Full error details:")
            return f"Error processing news query: {str(e)}"

    def get_capabilities(self) -> Dict[str, Any]:
        """Get agent capabilities."""
        logger.debug("Retrieving news agent capabilities")

        capabilities = {
            "name": "News Agent",
            "description": "Professional news agent for fetching and analyzing news",
            "tools": [
                {
                    "name": "web_search",
                    "description": "Search for general news and information",
                },
                {
                    "name": "get_breaking_news",
                    "description": "Get latest breaking news",
                },
                {
                    "name": "get_financial_news",
                    "description": "Get financial and market news",
                },
            ],
            "supported_queries": [
                "Latest news",
                "Breaking news",
                "Financial news",
                "Market updates",
                "Topic-specific news search",
            ],
        }

        logger.debug("Capabilities retrieved successfully")
        return capabilities
