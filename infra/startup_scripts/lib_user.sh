# -----------------------------------------------------------------------------
# geopoai_ensure_login_user — Verda images vary: some use root only, some use ubuntu.
# Many cuda-12.4 docker images have no ubuntu account; our stack expects /home/ubuntu.
# -----------------------------------------------------------------------------

geopoai_ensure_login_user() {
  if id -u ubuntu &>/dev/null 2>&1; then
    GEOPOAI_USER=ubuntu
    GEOPOAI_HOME=/home/ubuntu
  else
    echo "[geopoai:user] no ubuntu user on this image — creating ubuntu" >&2
    if ! useradd -m -s /bin/bash -U ubuntu 2>/dev/null; then
      echo "[geopoai:user] useradd failed; falling back to root" >&2
      GEOPOAI_USER=root
      GEOPOAI_HOME=/root
    else
      GEOPOAI_USER=ubuntu
      GEOPOAI_HOME=/home/ubuntu
    fi
  fi
  export GEOPOAI_USER GEOPOAI_HOME
  echo "[geopoai:user] GEOPOAI_USER=${GEOPOAI_USER} GEOPOAI_HOME=${GEOPOAI_HOME}" >&2
}

geopoai_run_as_user() {
  # Usage: geopoai_run_as_user "commands..."
  local cmd="$1"
  if [[ "${GEOPOAI_USER}" == root ]]; then
    bash -c "${cmd}"
  else
    sudo -u "${GEOPOAI_USER}" bash -c "${cmd}"
  fi
}
