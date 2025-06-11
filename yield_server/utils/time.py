from datetime import datetime, timezone

def get_current_time()->datetime:
    return datetime.now(timezone.utc)

def get_micro_timestamp()->int:
    return int(datetime.now(timezone.utc).timestamp() * 1_000_000)

def get_timestamp()->int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)

def convert_date_to_timestamp(date: datetime)->int:
    return int(date.timestamp() * 1000)

if __name__=="__main__":
    print(get_current_time())
    print(get_micro_timestamp())
    print(get_timestamp())