## Gestão de segredos

Para evitar que credenciais acabem na árvore do projeto (e, por consequência, no repositório), mantenha os arquivos sensíveis fora deste diretório e use variáveis de ambiente para apontar para eles.

### `.env` / variáveis

Crie um arquivo `.env` **fora** do projeto ou use o gerenciador de segredos da sua infraestrutura. As variáveis mínimas são:

```
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=app.exemplo.com,www.app.exemplo.com
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=3306
GS_BUCKET_NAME=...
GOOGLE_APPLICATION_CREDENTIALS=/caminho/fora/do/projeto/gcs-key.json
```

### Sem arquivo `gcs-key.json` no projeto

Se preferir não manter o arquivo físico em disco, defina `GOOGLE_APPLICATION_CREDENTIALS_JSON` com o conteúdo do JSON (puro ou codificado em Base64). O `settings.py` grava esse conteúdo em um arquivo temporário git-ignorável (`tmp/gcs-key.json`) apenas em tempo de execução e define automaticamente `GOOGLE_APPLICATION_CREDENTIALS` para esse caminho.

> **Importante:** nunca commitar `.env`, arquivos `.json` de credenciais ou qualquer outro segredo. O `.gitignore` já protege `tmp/`, `test_media/`, `.env`, `gcs-key.json` etc., mas a melhor prática é manter tudo fora do diretório do código.
