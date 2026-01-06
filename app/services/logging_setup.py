import logging
from logging.handlers import RotatingFileHandler


LOG_PATH = "app.log"

class UserContextFilter(logging.Filter):

    def filter(self, record):

        if not hasattr(record, "user_id"):
            record.user_id = "N/A"

        return True
    
class OrderContextFilter(logging.Filter):

    def filter(self, record):

        if not hasattr(record, "order_id"):
            record.order_id = "N/A"

        return True
    
class DeliveryContextFilter(logging.Filter):

    def filter(self, record):

        if not hasattr(record, "delivery_user_id"):
            record.delivery_user_id = "N/A"

        return True
    

class AdminContextFilter(logging.Filter):

    def filter(self, record):

        if not hasattr(record, "admin_user_id"):
            record.admin_user_id = "N/A"

        return True


def create_logger(name, formatter_str, filter=None):

    """"""

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if filter:
        logger.addFilter(filter) 

    formatter = logging.Formatter(formatter_str)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=5_000_000, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


logger_auth = create_logger(name="auth",
                            filter=UserContextFilter(),
                            formatter_str="%(asctime)s - %(levelname)s - user_id=%(user_id)s - %(message)s")

logger_nav = create_logger(name="nav",
                           filter=UserContextFilter(),
                           formatter_str="%(asctime)s - %(levelname)s - user_id=%(user_id)s - %(message)s")

logger_order = create_logger(name="order",
                             filter=OrderContextFilter(),
                             formatter_str="%(asctime)s - %(levelname)s - order_id=%(order_id)s - %(message)s")

logger_delivery = create_logger(name="delivery",
                                filter=DeliveryContextFilter(),
                                formatter_str="%(asctime)s - %(levelname)s - delivery_user_id=%(delivery_user_id)s - %(message)s")

logger_admin = create_logger(name="admin",
                            filter=AdminContextFilter(),
                            formatter_str="%(asctime)s - %(levelname)s - admin_user_id=%(admin_user_id)s - %(message)s")

logger_default = create_logger(name="default",
                               filter=None,
                               formatter_str="%(asctime)s - %(levelname)s - %(message)s")


def get_logger(name: str):

    return logging.getLogger(name)