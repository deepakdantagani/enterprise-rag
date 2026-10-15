#!/bin/bash
# Blocks reading or editing .env (it holds the Voyage, DeepSeek and OpenAI keys). Exit 2 = block, stderr goes to Claude.
file=$(jq -r '.tool_input.file_path // .tool_input.path // empty')
case "$(basename "$file")" in
  .env.example) exit 0 ;;
  .env|.env.*) echo "Access to .env is blocked. Name the variable you need instead; the code loads it with load_dotenv." >&2; exit 2 ;;
esac
exit 0
