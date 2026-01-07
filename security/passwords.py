from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash


# Paramètres recommandés
ph = PasswordHasher(
    time_cost=3,        # itérations
    memory_cost=64_000, # ~64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID        # Argon2id (recommandé)
)


def hash_password(plain_password: str) -> str:

    """Hache un mot de passe en utilisant Argon2id et retourne le hash sécurisé."""

    # -> ex: "$argon2id$v=19$m=65536,t=3,p=2$<sel>$<hash>"
    return ph.hash(plain_password)


def verify_password(plain_password: str, stored_hash: str) -> bool:

    """Vérifie si un mot de passe correspond à un hash Argon2id stocké."""

    try:
        ph.verify(stored_hash, plain_password)
        # Si les paramètres ont évolué, on pourra ré-hacher (voir ci-dessous)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False


def needs_rehash(stored_hash: str) -> bool:

    """Permet de migrer vers des paramètres plus forts avec le temps."""
    
    try:
        return ph.check_needs_rehash(stored_hash)
    except InvalidHash:
        return True
