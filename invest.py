#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import matplotlib.pyplot as plt

# Load investment data from a CSV file
#data = pd.read_csv('invest.csv', index_col='Date')
data = pd.read_csv('invest.csv')
data['Total_balance'] = data[['LQ', 'HF', 'JHL', 'GZ']].sum(axis=1).round(2)
#print(data['Date'])
#print(data)
data.to_excel('invest_output.xlsx')

# 设置中文字体
# 需要执行sudo apt-get install fonts-wqy-zenhei
# sudo fc-cache -f -v       
#plt.rcParams['font.family'] = 'SimHei'
plt.rcParams['font.family'] = "WenQuanYi Zen Hei"
plt.figure(figsize=(10, 6))
plt.plot(data['index'], data['Total_balance'], marker='o', label='Total Balance', color='blue')
plt.plot(data['index'], data['LQ'], marker='o', label='LQ', linestyle='--')
plt.plot(data['index'], data['HF'], marker='o', label='HF', linestyle='--')
plt.plot(data['index'], data['JHL'], marker='o', label='JHL', linestyle='--')
plt.plot(data['index'], data['GZ'], marker='o', label='GZ', linestyle='--')
for i in enumerate(data['Total_balance']):
    plt.text(data['index'][i[0]] + 0.1, data['Total_balance'][i[0]] + 0.1, str(data['Total_balance'][i[0]]), fontsize=9)
# 设置非数字轴标签
plt.xticks(data['index'], data['Date'], rotation=45)
#plt.title('Investment Portfolio Over Weeks')
plt.xlabel('周')
plt.ylabel('收益')
plt.ylim(0)
plt.legend()
plt.grid()
plt.savefig('invest_report.png')
plt.show()
