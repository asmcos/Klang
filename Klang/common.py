
import argparse
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument("--offset", help="开始执行的位置",default='0')
parser.add_argument("--end", help="日期",default='0')
parser.add_argument("--start", help="日期",default='2020-10-01')

args = parser.parse_known_args()
if len(args) > 1:
    args = args[0]

end = args.end
start = args.start

def gettoday():
    today = datetime.now()
    return str(today.year) + '-' +str(today.month) +'-'+ str(today.day)

if end== '0':
    end = gettoday()

