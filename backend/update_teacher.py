import sqlite3

def main():
    conn = sqlite3.connect('childtrack_dev.db')
    cursor = conn.cursor()
    
    # Get Admin hash
    hash_pwd = cursor.execute('SELECT hashed_password FROM users WHERE email="admin@childtrack.local"').fetchone()[0]
    
    # Update teacher hash
    cursor.execute('UPDATE users SET hashed_password=? WHERE email="teacher@childtrack.local"', (hash_pwd,))
    
    conn.commit()
    print('Password sync complete.')

if __name__ == '__main__':
    main()
