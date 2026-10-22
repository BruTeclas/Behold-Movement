#!/usr/bin/env python3
"""Empacota o site para o Coolify sem Git (deploy/coolify.Dockerfile).

O site publicado é a pasta site/ (index.html, sites-incriveis.css e
sites-incriveis.js), editada diretamente. Este script NÃO gera nem altera
site/index.html: só embute a pasta site/ e a configuração do nginx num
Dockerfile autocontido, para colar no Coolify (recurso "Dockerfile", sem Git).

O deploy normal vem do Git (Dockerfile da raiz), e esse não depende deste script.

behold-movement.html é a primeira versão do site (formato Artifact do Claude),
mantida só como referência; ela não é mais publicada.

Uso: python3 scripts/build-site.py
"""
import base64
import io
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def write_coolify_dockerfile() -> None:
    arquivos = sorted(p for p in SITE.rglob("*") if p.is_file())
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        itens = [(p, "usr/share/nginx/html/" + p.relative_to(SITE).as_posix()) for p in arquivos]
        itens.append((ROOT / "deploy" / "nginx.conf", "etc/nginx/conf.d/default.conf"))
        for src, dest in itens:
            info = tar.gettarinfo(str(src), arcname=dest)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mode = 0o644
            info.mtime = 0
            with open(src, "rb") as fh:
                tar.addfile(info, fh)
    payload = base64.b64encode(buf.getvalue()).decode()

    dockerfile = f"""# Behold Movement: site estático (gerado por scripts/build-site.py, não editar à mão).
# Coolify: New Resource > Dockerfile (sem Git) > cole este arquivo inteiro.
FROM nginx:1.27-alpine
RUN echo "{payload}" | base64 -d | tar -xz -C /
EXPOSE 80
"""
    path = ROOT / "deploy" / "coolify.Dockerfile"
    path.write_text(dockerfile, encoding="utf-8")
    nomes = ", ".join(p.relative_to(SITE).as_posix() for p in arquivos)
    print(f"ok: {path.relative_to(ROOT)} ({len(dockerfile.encode())} bytes) com {nomes}")


if __name__ == "__main__":
    write_coolify_dockerfile()
