def migrate(cr, version):
    """Migrate print_hour from single-digit '0'-'9' to two-digit '00'-'09' format.
    Set print_minute default for existing records.
    """
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'tpv_pedido_config'
          AND column_name = 'print_minute'
    """)
    if cr.fetchone():
        cr.execute("""
            UPDATE tpv_pedido_config
            SET print_hour = LPAD(print_hour, 2, '0'),
                print_minute = COALESCE(NULLIF(print_minute, ''), '00')
            WHERE print_hour IS NOT NULL
              AND LENGTH(print_hour) = 1
        """)
        cr.execute("""
            UPDATE tpv_pedido_config
            SET print_minute = '00'
            WHERE print_minute IS NULL OR print_minute = ''
        """)

    # Enforce NOT NULL on tpv.backup.file required fields
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'tpv_backup_file'
          AND column_name IN ('name', 'date')
          AND is_nullable = 'YES'
    """)
    for col, in cr.fetchall():
        cr.execute('ALTER TABLE tpv_backup_file ALTER COLUMN %s SET NOT NULL' % col)
