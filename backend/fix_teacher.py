import sqlite3

def main():
    conn = sqlite3.connect('childtrack_dev.db')
    cursor = conn.cursor()
    row = cursor.execute('SELECT id FROM users WHERE email="teacher@childtrack.local"').fetchone()
    if row:
        new_id = row[0].replace('-', '')
        cursor.execute('UPDATE users SET id=? WHERE email="teacher@childtrack.local"', (new_id,))
        conn.commit()
        print('Fixed UUID format for teacher.')
    else:
        print('Teacher not found')

if __name__ == '__main__':
    main()
