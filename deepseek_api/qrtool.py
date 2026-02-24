from PIL import Image

def qr_print(image_path):
    img = Image.open(image_path).convert('L')
    
    padding = 30
    box_size = 10
    grid_count = 41 
    
    img_cropped = img.crop((padding, padding, 470 - padding, 470 - padding))
    
    for y in range(grid_count):
        for x in range(grid_count):
            px_x = x * box_size + (box_size // 2)
            px_y = y * box_size + (box_size // 2)
            
            pixel_value = img_cropped.getpixel((px_x, px_y))
            
            # bit 为 1 是黑色，bit 为 0 是白色
            bit = 1 if pixel_value < 128 else 0
            
            if bit:
                # 打印黑色背景的两个空格
                print('\033[40m  \033[0m', end='')
            else:
                # 打印白色背景的两个空格
                print('\033[47m  \033[0m', end='')
        print() # 换行

if __name__ == '__main__':
    qr_print(r'C:\Users\magic\Documents\projects\DeepSeek\071khzSI17CVG__W_sample.jpg')