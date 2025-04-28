import pandas as pd
import psycopg2
import os

# 数据库连接
conn = psycopg2.connect(
    dbname='newlink',
    user='dws_finance_rw',
    password='e8jtA9QYNFtUnFch',
    host='10.61.11.179',
    port='8000'
)

# 要查询的月份
months = ['2024-09','2024-10','2024-11','2024-12']

# SQL查询列表
tables = [
    'tuanyou_partition_shouru_new_tmp',
    # 'tuanyou_partition_shoudan_new_tmp',
    'tuanyou_partition_chengben_new_tmp'
    # 'tuanyou_partition_jiesuan_new_tmp'
    # 'tuanyou_partition_driver_shoudan_new',
    # 'tuanyou_partition_driver_jiesuan_new',
    # 'tuanyou_partition_driver_shouru_chengben_new'
]

# 处理每个月份的数据
for month in months:
    print(f"\n处理 {month} 月份的数据")
    
    # 创建月份文件夹
    folder = f"export_results/{month}"
    os.makedirs(folder, exist_ok=True)
    
    # 处理每个表
    for table in tables:
        print(f"正在导出表: {table}")
        
        # 执行查询
        sql = f"SELECT * FROM finance.{table} WHERE data_month='{month}'"
        try:
            df = pd.read_sql(sql, conn)

            # print(df)
            
            #导出到Excel
            output_file = f"{folder}/{table}.xlsx"
            df.to_excel(output_file, index=False)
            print(f"已保存到: {output_file}")

        except Exception as e:
            print(f"处理表 {table} 时出错: {e}")


# 关闭数据库连接
conn.close()
print("\n所有数据导出完成！") 