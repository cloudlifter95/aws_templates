-- select most recent rows from a table.
Select
    a.*
from
    observability.cflogs_table a
    inner join (
        select
            stackname,
            max(time) as maxtime
        from
            observability.cflogs_table
        group by
            stackname
    ) b on a.stackname = b.stackname
    and a.time = b.maxtime;

Select
    a.*
from
    mydatabase.mytable a
    inner join (
        select
            uname,
            max(dateupdated) as max_date
        from
            mydatabase.mytable
        group by
            uname
    ) b on a.uname = b.uname
    and a.dateupdated = b.maxdate;