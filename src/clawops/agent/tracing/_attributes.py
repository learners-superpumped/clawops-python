"""OTEL span attribute key 상수."""

# Call
CALL_ID = "call.id"
CALL_FROM = "call.from"
CALL_TO = "call.to"
CALL_DURATION_MS = "call.duration_ms"

# GenAI (OTEL semantic conventions)
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_REQUEST_VOICE = "gen_ai.request.voice"
GEN_AI_RESPONSE_ID = "gen_ai.response.id"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# MCP
MCP_SERVER_TYPE = "mcp.server.type"
MCP_SERVER_COMMAND = "mcp.server.command"
MCP_SERVER_URL = "mcp.server.url"
MCP_TOOLS_COUNT = "mcp.tools.count"
MCP_TOOL_NAME = "mcp.tool.name"
MCP_TOOL_IS_ERROR = "mcp.tool.is_error"

# Tool
TOOL_NAME = "tool.name"
TOOL_SOURCE = "tool.source"
TOOL_DURATION_MS = "tool.duration_ms"

# STT / TTS
STT_MODEL = "stt.model"
STT_LANGUAGE = "stt.language"
STT_DURATION_MS = "stt.duration_ms"
TTS_MODEL = "tts.model"
TTS_VOICE = "tts.voice"
TTS_DURATION_MS = "tts.duration_ms"
