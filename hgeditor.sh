#!/bin/sh

# The default editor to use for 'hg commit' at khan academy.  It calls
# the normal editor (which is passed as the arg to this script) but
# adds some automatic fields, such as 'Test Plan'.

ED="$1"
FILE="$2"
TMP="$FILE.hg_templated_editor.$$.txt"

MD5SUM=`/usr/bin/which md5sum md5 | head -n1`

if [ -n "$3" ]; then
  echo "Too many arguments to $0: '$1' '$2' '$3' ..."
  echo "Should have two args only: editor and filename."
  exit 255
fi

cleanup_exit() {
    /bin/rm -f "$TMP"
}

# Cleanup temporary file on exit or abnormal interruption
trap "cleanup_exit" 0 # normal exit
trap "exit 255" 1 2 3 6 15 # HUP INT QUIT ABRT TERM

# $TMP should match the permissions of $FILE
umask 077

# Check if there's already a commit message (in the case of an amend)
if grep . "$FILE" | grep -q -v "^HG:"; then
    # Just leave the message as is
    cp "$FILE" "$TMP"
else
    if [ `hg parents --template x | wc -c` -gt 1 ]; then
        echo "merge"
        echo ""
        changes_required=0
    else
        # Prepend the custom template.  Leave space for one-line and full
        # summaries.
        echo "<one-line summary, followed by blank line and full summary>"
        echo ""
        echo "Test Plan:"
        echo "<see below>"
        echo ""
        echo "HG: --"
        echo "HG: For 'Test Plan:', list the commands you ran or process you"
        echo "HG:   followed to test this change."
        # TODO(csilvers): figure out automatically if this change is likely to
        # be a new review or an update to an existing review.
        echo "HG: If this commit is adding to an existing review, delete the"
        echo "HG: 'Test Plan:' lines and replace them with 'Review: Kxxx'."
        echo "HG:"
        changes_required=1
    fi \
    > "$TMP" || exit $?

    # Append the original template.  Get rid of its starting blank line.
    grep . "$FILE" >> "$TMP"
fi

CHECKSUM=`"$MD5SUM" "$TMP"`

$ED "$TMP" || exit $?

# Detect if no change was made to the commit message.
if [ "$changes_required" = "1" -a "$CHECKSUM" = "`"$MD5SUM" "$TMP"`" ]; then
  # On exit 0 original $FILE remains unchanged, causing hg to complain.
  exit 0
fi

/bin/mv -f "$TMP" "$FILE"
