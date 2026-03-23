FROM debian:bookworm

ARG TZ
ENV TZ="$TZ"
ENV GIT_DELTA_VERSION=0.18.2
ARG CLAUDE_CODE_VERSION=latest

# Install development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
  less \
  git \
  procps \
  sudo \
  build-essential \
  pkg-config \
  autoconf \
  automake \
  libtool \
  ffmpeg \
  fzf \
  zsh \
  man-db \
  unzip \
  gnupg2 \
  gh \
  jq \
  nano \
  vim \
  curl \
  wget \
  ca-certificates \
  libnspr4 \
  libnss3 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libatspi2.0-0 \
  libxcomposite1 \
  libxdamage1 \
  locales-all \
  ripgrep \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create node user (matching devcontainer convention)
RUN groupadd --gid 1000 node && \
  useradd --uid 1000 --gid node --shell /bin/zsh --create-home node

# Ensure node user has access to /usr/local/share
RUN mkdir -p /usr/local/share/npm-global && \
  chown -R node:node /usr/local/share

ARG USERNAME=node

# Persist shell history
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  && mkdir /commandhistory \
  && touch /commandhistory/.bash_history \
  && chown -R $USERNAME /commandhistory

# Set `DEVCONTAINER` environment variable to help with orientation
ENV DEVCONTAINER=true

# Create workspace and config directories (needed for volume mounts)
RUN mkdir -p /workspace /home/node/.claude /home/node/.codex /workspace/.venv_devcontainer /home/node/.cache/uv && \
  chown -R node:node /workspace /home/node/.claude /home/node/.codex /home/node/.cache

WORKDIR /workspace

# Install git-delta for better diffs
RUN ARCH=$(dpkg --print-architecture) && \
  wget "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  sudo dpkg -i "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  rm "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install bun
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun
COPY --from=oven/bun:latest /usr/local/bin/bunx /usr/local/bin/bunx

# Set up non-root user
USER node
ENV ZSH_IN_DOCKER_VERSION=1.2.1

# Install Emscripten SDK (for gifsicle-bin WASM builds)
RUN git clone --depth 1 https://github.com/emscripten-core/emsdk.git /home/node/.emsdk && \
  cd /home/node/.emsdk && ./emsdk install latest && ./emsdk activate latest
ENV PATH="/home/node/.emsdk:/home/node/.emsdk/upstream/emscripten:$PATH"

# Install mise (manages Python + Node.js versions)
RUN curl https://mise.run | sh

# Set up PATH for mise and other tools
ENV PATH="/home/node/.local/bin:/home/node/.local/share/mise/shims:$PATH"
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH="$PATH:/usr/local/share/npm-global/bin"
ENV PATH="$PATH:/home/node/.bun/bin"

# Install Python 3.13 and Node.js 24 via mise
RUN mise use --global python@3.13 node@24

# Set the default shell to zsh
ENV SHELL=/bin/zsh

# Fix locale warnings
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# Set the default editor
ENV EDITOR=nano
ENV VISUAL=nano

# Explicitly set uv venv path so we don't stomp on host-local .venv
# This should be set as a volume-mount in the devcontainer to avoid recreating at each boot
ENV UV_PROJECT_ENVIRONMENT=/workspace/.venv_devcontainer

# uv cache settings - use copy mode since cache is on a different volume
ENV UV_CACHE_DIR=/home/node/.cache/uv
ENV UV_LINK_MODE=copy

# Install zsh with powerlevel10k theme
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v${ZSH_IN_DOCKER_VERSION}/zsh-in-docker.sh)" -- \
  -p git \
  -p fzf \
  -a "source /usr/share/doc/fzf/examples/key-bindings.zsh" \
  -a "source /usr/share/doc/fzf/examples/completion.zsh" \
  -a "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  -a 'eval "$(mise activate zsh)"' \
  -x

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- $CLAUDE_CODE_VERSION

# Install codex and just via bun
RUN bun i -g @openai/codex rust-just

# Install agent-browser skill reqs (see devcontainer.json for playwright+agent-browser chromium install)
RUN bun i -g agent-browser

# Install skills from skills-lock.json
RUN bunx skills experimental_install

# uv sync runs in devcontainer.json postStartCommand because
# the workspace is bind-mounted at container runtime (not available during docker build).
