import subprocess, sys

def main():
    args = sys.argv
    # folder to make movie, dpi, x, y
    dirs = args[1]
    dpi = args[2]
    x = args[3]
    y = args[4]

    stdout = subprocess.check_output(['ffmpeg', '-encoders', '-v', 'quiet'])

    for encoder in ['libx264', 'mpeg4', 'mpeg']:
        if encoder in stdout:
            break
    else:
        return
    subprocess.call(
        ["ffmpeg", "-framerate", "10", "-pattern_type", "glob", "-i", dirs + '*.png', '-c:v', encoder, '-vf',
         'scale=' + str(int(x)*int(dpi)) + ':' + str(int(y)*int(dpi)) + ' ,format=yuv420p', '-y', dirs + 'movie.mp4'])


if __name__ == "__main__":
    main()