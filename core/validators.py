from django.core.exceptions import ValidationError

def validate_file_size(value):
    """
    Validador customizado para garantir que o arquivo não passe de 2MB.
    """
    filesize = value.size
    
    # 2 MB = 2 * 1024 * 1024 bytes
    if filesize > 2097152: 
        raise ValidationError("O tamanho máximo do arquivo permitido é 2MB.")
    else:
        return value